#!/usr/bin/python3
#coding=utf-8

########################################################################
# Скрипт копирования файлов с удаленного сервера
# Версия 1.1
# Скрипач: rootik
########################################################################


import paramiko
import scp
from configobj import ConfigObj
import sys
from getpass import getpass
import os
import io
import datetime
import re
import time
import tqdm
import gzip
import shutil
from stat import S_ISDIR,S_ISREG

#Загружаем конфиг

config_path='./config_copyArtifacts.ini'
config = ConfigObj(config_path, list_values=False)
download_dirs = config['general']['download_dirs'].split(',')

required_params = {}
hosts_creds = {}
unpack_files = {}


#Получение свободного места на диске в МБ
def check_free_space(path):
	osdata = os.statvfs(path)
	freespace = int(osdata.f_bavail*osdata.f_bsize/1024/1024)
	return freespace


#Подключение ssh с паролем
def ssh_conn_pass(host,user,password,port):
	ssh = paramiko.SSHClient()
	ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
	ssh.connect(hostname=host, username=user, password=password, port=port, timeout=3)
	return ssh

#Подключение ssh с rsa
def ssh_conn_key(host,user,keypath,port):
	pkey = paramiko.RSAKey.from_private_key_file(keypath)
	ssh = paramiko.SSHClient()
	ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
	try:
		ssh.connect(host, username=user, pkey=pkey, port=port, timeout=3)
	except paramiko.ssh_exception.AuthenticationException:
		ssh.connect(host, username=user, pkey=pkey, port=port, timeout=3, disabled_algorithms=dict(pubkeys=["rsa-sha2-512","rsa-sha2-256"]))
	return ssh

#Добавление даты в поля с датой
def add_date_to(attribute, date):
	if '%date%' in attribute:
		if attribute.split(',')[-1] != '':
			date_format = attribute.split(',')[-1]
			attribute = attribute.replace(','+date_format,'')
			attribute = attribute.replace('%date%', date_obj.strftime(date_format))
		else:
			print('Не удалось найти формат даты для шаблона файла!')
			return None
	return attribute


#Создание нехватающих локальних директорий
def check_local_path(path):
	exists_path = ''
	for path_part in path.split('/')[1:]:
		exists_path += '/'+path_part
		if not (os.path.exists(exists_path)):
			os.mkdir(exists_path)

def normal_path(path):
	if path[-1] != '/':
		path += '/'
	return path


#Увеличение размера при распаковке
def get_compress_level(path):
	compress_size = os.stat(path).st_size
	unpack_size = len(gzip.open(path, 'rb').read())

	compressing = float(unpack_size/compress_size)

	if (compressing - int(compressing)) > 0:
		compressing = int(compressing) + 1
	else:
		compressing = int(compressing)

	return compressing


#Подсчет места под архивы
def get_space_for_unpack(list_files):
	#Колхозное вычисление степени сжатия
	compress_level = -1.0
	for f in list_files:
		if f.split('.')[-1] != 'gz':
			continue
		if compress_level != -1:
			break
		compress_level = get_compress_level(f)

	size = 0
	for f in list_files:
		if f.split('.')[-1] != 'gz':
			continue
		info = os.stat(f)
		size += info.st_size*compress_level
	size = int(size/1024/1024)

	return size


#Распаковка архивов
def unpack_gz(list_files, suffix):
	for f in tqdm.tqdm(list_files):
		if f.split('.')[-1] != 'gz':
			continue
		gz_bytes = gzip.open(f, 'rb')
		outfile = f.replace('.gz','')
		if suffix != '':
			outfile += suffix
		unpack_file = open(outfile, 'wb')
		shutil.copyfileobj(gz_bytes, unpack_file)
		gz_bytes.close()
		unpack_file.close()
		os.remove(f)




#Формирование списка файлов
def get_files_list(list_func, src_path, need_date_min, config):

	global moving_files
	global moving_size

	src_path = normal_path(src_path)

	files_list = list_func(src_path)

	for f in files_list:
		#Рекурсивный поиск по подкаталогам
		if config['recursive_search'] == 'True' and S_ISDIR(f.st_mode):
			get_files_list(list_func, src_path+f.filename, need_date_min, config)


		if S_ISREG(f.st_mode):
			#Проверка имени по шаблону
			if (re.match(config['file_pattern'],f.filename) == None):
				continue
			if config['recursive_search'] == 'True'  and (re.match(normal_path(config['remote_path'])+config['subdir_pattern'], src_path) == None):
				continue
			#Проверка вхождения времени изменений в диапазон
			if (config['mtime_choice'] == 'True'):
				mtime = datetime.datetime.fromtimestamp(f.st_mtime)
				need_date_max = need_date_min + datetime.timedelta(days=int(config['days_count']))
				if (mtime < need_date_min) or (mtime > need_date_max):
					continue

			moving_size += f.st_size

			#Формируем пути для локальных файлов с повторением структуры или без
			if config['repeat_struct'] == 'True':
				moving_files[src_path+f.filename] = normal_path(config['local_path']) + (src_path).replace(normal_path(config['remote_path']), "")
				moving_files[src_path+f.filename] = normal_path(moving_files[src_path+f.filename]) + f.filename
			else:
				moving_files[src_path+f.filename] = normal_path(config['local_path'])+f.filename
			
			#Если есть суффикс и распаковки потом не будет, ставим его сразу в имя файла
			if config['unpack_gz'] != 'True' and config['outfile_suffix'] != '':
				moving_files[src_path+f.filename] += config['outfile_suffix']




#Получение списка нужных файлов и их общего размера
def list_dir(ssh_obj, need_date, params):

	global moving_files
	global moving_size


	check_dirs = []

	sftp = ssh_obj.open_sftp()
	files_func = sftp.listdir_attr

	print('Подготовка списка подходящих файлов...')

	#Формируем список файлов
	get_files_list(files_func, params['remote_path'], need_date, params)

	#Проверяем все пути для скачивания
	if params['repeat_struct'] == 'True':
		for path in moving_files.values():
			dst_path = path.replace(path.split('/')[-1], "")
			if dst_path not in check_dirs:
				check_dirs.append(dst_path)
	else:
		check_dirs.append(params['local_path'])

	for path in check_dirs:
		check_local_path(path)


	if ssh_obj != 'local':
		sftp.close()

	moving_size = int(moving_size/1024/1024)



#Загрузка файлов
def download_files(ssh_obj, host, protocol):

	global moving_files


	#Определяем функцию: копирование по сети для удален.узлов, линкование - для локального копирования
	if host == 'localhost':
		copy_func = os.link
	else:
		if protocol == 'ssh':
			conn = scp.SCPClient(ssh_obj.get_transport())
		if protocol == 'sftp':
			conn = ssh_obj.open_sftp()
		copy_func = conn.get

	for src_path in tqdm.tqdm(moving_files):
		copy_func(src_path,moving_files[src_path])


	if host != 'localhost':
		conn.close()




#Берем параметры из секции general для каждого направления, при наличии оверрайда в секции берем его
for direct in download_dirs:
	if direct in config:

		required_params[direct] = {'host' : '',
					'username' : '',
					'port' : '22',
					'protocol' : 'ssh',
					'download_date' : '',
					'days_count' : '1',
					'remote_path' : '',
					'local_path' : '',
					'keypath' : '',
					'file_pattern' : '',
					'outfile_suffix' : '',
					'mtime_choice' : 'False',
					'unpack_gz' : 'False',
					'recursive_search' : 'False',
					'subdir_pattern' : '.*',
					'repeat_struct' : 'False'}

		for param in required_params[direct]:
			if param in config[direct]:
				required_params[direct][param] = config[direct][param]
			elif param in config['general']:
				required_params[direct][param] = config['general'][param]

		if required_params[direct]['keypath'] == '':
			hosts_creds[required_params[direct]['host']] = ''
#Пароли для хостов
for host in hosts_creds:
	hosts_creds[host] = getpass('Пароль для подключения к хосту '+host+': ')


#Тело выгрузки
for direct in required_params:
	print('----------------------------------------------------------------------------------------')
	print('Начало выгрузки ' + direct + '...')
	if required_params[direct]['keypath'] != '':
		try:
			print('Попытка подключения к хосту ' + required_params[direct]['host'] + '...')
			ssh_conn = ssh_conn_key(required_params[direct]['host'],
						required_params[direct]['username'],
						required_params[direct]['keypath'],
						required_params[direct]['port'])
		except:
			print('Не удалось подключиться к хосту ' + required_params[direct]['host'])
			print('Будет пропущена выгрузка ' + direct)
			continue
	elif required_params[direct]['host'] in hosts_creds:
		try:
			print('Попытка подключения к хосту ' + required_params[direct]['host'] + '...')
			ssh_conn = ssh_conn_pass(required_params[direct]['host'],
						required_params[direct]['username'],
						hosts_creds[required_params[direct]['host']],
						required_params[direct]['port'])
		except:
			print('Не удалось подключиться к хосту ' + required_params[direct]['host'])
			print('Будет пропущена выгрузка ' + direct)
			continue
	#Получение нужной даты
	date_obj = datetime.datetime.strptime(required_params[direct]['download_date'], '%Y/%m/%d')
	#Подставляем даты в параметры
	for attr in ['remote_path', 'local_path', 'file_pattern', 'subdir_pattern']:
		required_params[direct][attr] = add_date_to(required_params[direct][attr], date_obj)
		if required_params[direct][attr] == None:
			print('Будет пропущена выгрузка ' + direct)
			continue

	#Формируем список скачиваемых файлов
	moving_files = {}
	moving_size = 0

	list_dir(ssh_conn, date_obj, required_params[direct])

	free_space = check_free_space(required_params[direct]['local_path'])

	if moving_size >= free_space and ssh_conn != 'local':
			print('Недостаточно свободно места в локальном хранилище для загрузки! ' + str(moving_size - free_space) + 'МБ')
			print('Будет пропущена выгрузка ' + direct)
			continue

	print('Из: ' + required_params[direct]['remote_path'] + ' Объем:' + str(moving_size) + 'МБ ' + str(len(moving_files)) + ' файлов')
	print('В: ' + required_params[direct]['local_path'] + ' Свободно:' + str(free_space) + 'МБ')

	download_files(ssh_conn,
		required_params[direct]['host'],
		required_params[direct]['protocol'])

	if required_params[direct]['unpack_gz'] == 'True':
		unpack_files[direct] = moving_files.values()


	ssh_conn.close()
	print('----------------------------------------------------------------------------------------')



for direct in unpack_files:
	print('----------------------------------------------------------------------------------------')
	print('Распаковка данных ' + direct + '...')

	free_space = check_free_space(required_params[direct]['local_path'])

	unpack_space = get_space_for_unpack(unpack_files[direct])

	if unpack_space >= free_space:
		print('Недостаточно свободно места в локальном хранилище для распаковки! ' + str(unpack_space - free_space) + 'МБ')
		print('Будет пропущена распаковка ' + direct)
		continue

	unpack_gz(unpack_files[direct], required_params[direct]['outfile_suffix'])


