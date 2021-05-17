#!/usr/bin/env python

import MySQLdb
from os import getenv
from sys import exit
from time import sleep


MAX_TRIES = getenv('DB_MAX_TRIES', 20)
INTERVAL = getenv('DB_INTERVAL', 5)
DB_HOST = getenv('DB_HOST', 'database')


def run():
    connected = False
    attempt = 0

    while not connected and attempt < MAX_TRIES:
        try:
            db = MySQLdb.connect(host=DB_HOST, user='root')
            connected = True
            print('Database server connected!')
        except MySQLdb.MySQLError:
            attempt += 1
            print('Database server not connected. Trying again in {} seconds...'.format(INTERVAL))
            sleep(INTERVAL)

    if connected:
        c = db.cursor()
        try:
            c.execute('USE keystone;')
            print('Database keystone already exists!')
        except MySQLdb.MySQLError:
            print('Database keystone does not exist. Creating...')
            c.execute('CREATE DATABASE keystone DEFAULT CHARACTER SET utf8 DEFAULT COLLATE utf8_general_ci;')
            print('Database keystone created!')

        try:
            c.execute("CREATE USER 'root'@'10.5.0.6';")
            c.execute("GRANT ALL PRIVILEGES ON *.* TO 'root'@'10.5.0.6' WITH GRANT OPTION;")
        except Exception:
            pass

        exit(0)

    exit(1)


if __name__ == '__main__':
    run()
