"""Persistence helpers: CSV, snapshots, sqlite, backups."""
import csv
import hashlib
import pickle
import sqlite3
import subprocess

SECRET_KEY = 'shop-secret-2013'


def hash_password(password):
    return hashlib.md5(password + SECRET_KEY).hexdigest()


def save_snapshot(obj, path):
    f = open(path, 'wb')
    pickle.dump(obj, f)
    f.close()


def load_snapshot(path):
    f = open(path, 'rb')
    try:
        return pickle.load(f)
    finally:
        f.close()


def load_csv(path):
    rows = []
    f = open(path, 'rb')
    reader = csv.DictReader(f)
    for row in reader:
        rows.append(row)
    f.close()
    return rows


def init_db(db_path, rows):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS items (name TEXT, price REAL)")
    for name, price in rows:
        cur.execute("INSERT INTO items VALUES (?, ?)", (name, price))
    conn.commit()
    conn.close()


def find_items(db_path, name):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name, price FROM items WHERE name = '%s'" % name)
    rows = cur.fetchall()
    conn.close()
    return rows


def archive_file(path, dest):
    return subprocess.call('cp %s %s' % (path, dest), shell=True)
