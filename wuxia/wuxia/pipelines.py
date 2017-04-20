# -*- coding: utf-8 -*-

# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: http://doc.scrapy.org/en/latest/topics/item-pipeline.html
import json
import re
import logging
import sqlite3 as lite
import pymongo
from scrapy.exceptions import DropItem
from wuxia.items import BookItem, ChapterItem

class IdPipeline(object):
    def process_item(self, item, spider):
        if item['_id']:
            return item
        else:
            logging.error("Id is missing in %s" % item)
            raise DropItem("Missing ID in %s" % item)

class DuplicatedPipeline(object):

    def __init__(self):
        self.books_seen = set()
        self.chapters_seen = set()

    def process_item(self, item, spider):
        if isinstance(item, BookItem):
            if item['_id'] in self.books_seen:
                logging.error("Duplicate book found: %s" % item)
                raise DropItem("Duplicate book found: %s" % item)
            else:
                self.books_seen.add(item['_id'])
        elif isinstance(item, ChapterItem):
            if item['_id'] in self.chapters_seen:
                logging.error("Duplicate book found: %s" % item)
                raise DropItem("Duplicate chapter found: %s" % item)
            else:
                self.chapters_seen.add(item['_id'])
        return item

class BookNamePipeline(object):
    def process_item(self, item, spider):
        check_col_name = 'name'
        if isinstance(item,ChapterItem):
            check_col_name = 'parent_book_name'
        # If this is a book, the name should contain index, else drop it
        if "Index" in item[check_col_name] or "Table of Contents" in item[check_col_name] or "Sovereign of the Three Realms" in item[check_col_name]:
            # Get rid of (Chinese Name)
            item[check_col_name] = re.sub(r"\s*\(.+\)","",item[check_col_name])
            # Get rid of - Index
            item[check_col_name] = re.sub(r"\s*\W*\s*Index","",item[check_col_name])
            # Get rid of Table of Contents
            item[check_col_name] = re.sub(r"T\w+\s\w+\sC\w+","",item[check_col_name])
            # Get rid of -
            item[check_col_name] = re.sub(r"\s\W\s*","",item[check_col_name])
        else:
            logging.error("This is not a book, missing index in %s" % item)
            raise DropItem("This is not a book, missing index in %s" % item)
        return item

con = None  # sqlite db connection

class SqlitePipeline(object):

    def __init__(self):
        self.setupDBCon()
        self.dropTable()
        self.createTable()

    def process_item(self, item, spider):
        # If it is BookItem
        if isinstance(item, BookItem):
            try:
                self.cur.execute('insert into books values(?,?,?,?,?,?,?)',(item['id'],item['name'],item['description'],item['published_time'],item['modified_time'],item['cover_url'],item['likes']))
                self.con.commit()
            except:
                print("Failed to insert book: %s" % item)
        elif isinstance(item, ChapterItem):
            try:
                self.cur.execute('insert into chapters values(?,?,?,?,?,?)',(item['id'],item['name'],item['parent_book_id'],item['parent_book_name'],item['article_html'],item['article_footer']))
                self.con.commit()
            except:
                print("Failed to insert chapter: %s" % item)
        return item

    def setupDBCon(self):
        self.con = lite.connect('wuxia.db')
        self.cur = self.con.cursor()

    def __del__(self):
        self.closeDB()

    def createTable(self):
        self.cur.execute("""create table if not exists books (id INTEGER PRIMARY KEY NOT NULL,name TEXT NOT NULL,description TEXT NOT NULL,published_time TEXT NOT NULL,modified_time TEXT NOT NULL)""")
        self.cur.execute("""create table if not exists chapters (id INTEGER PRIMARY KEY NOT NULL,name TEXT NOT NULL, parent_book_id INTEGER NOT NULL, parent_book_name TEXT NOT NULL, article_html TEXT NOT NULL, article_footer TEXT)""")

    def dropTable(self):
        self.cur.execute("DROP TABLE IF EXISTS books")
        self.cur.execute("DROP TABLE IF EXISTS chapters")

    def closeDB(self):
        self.con.close()


class MongoPipeline(object):

    books_collection_name = 'books'
    chapters_collection_name = 'chapters'

    def __init__(self, mongo_uri, mongo_db):
        self.mongo_uri = mongo_uri
        self.mongo_db = mongo_db

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            mongo_uri = crawler.settings.get('MONGODB_URI'),
            mongo_db = crawler.settings.get('MONGODB_DB')
        )

    def open_spider(self, spider):
        self.client = pymongo.MongoClient(self.mongo_uri)
        self.db = self.client[self.mongo_db]

    def close_spider(self, spider):
        self.db[self.books_collection_name].create_index(["likes", pymongo.DESCENDING])
        self.db[self.chapters_collection_name].create_index(["parent_book_id", pymongo.ASCENDING])
        self.client.close()

    def process_item(self,item, spider):
        if isinstance(item, BookItem):
            self.db[self.books_collection_name].insert(dict(item))
        elif isinstance(item, ChapterItem):
            self.db[self.chapters_collection_name].insert(dict(item))
        return item
