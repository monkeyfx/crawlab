import itertools
import os
import re

import requests
from datetime import datetime, timedelta

from bson import ObjectId
from lxml import etree

from constants.spider import FILE_SUFFIX_LANG_MAPPING, LangType, SUFFIX_IGNORE, SpiderType, QueryType, ExtractType
from constants.task import TaskStatus
from db.manager import db_manager


def get_lang_by_stats(stats: dict) -> LangType:
    """
    Get programming language provided suffix stats
    :param stats: stats is generated by utils.file.get_file_suffix_stats
    :return:
    """
    try:
        data = stats.items()
        data = sorted(data, key=lambda item: item[1])
        data = list(filter(lambda item: item[0] not in SUFFIX_IGNORE, data))
        top_suffix = data[-1][0]
        if FILE_SUFFIX_LANG_MAPPING.get(top_suffix) is not None:
            return FILE_SUFFIX_LANG_MAPPING.get(top_suffix)
        return LangType.OTHER
    except IndexError as e:
        pass


def get_spider_type(path: str) -> SpiderType:
    """
    Get spider type
    :param path: spider directory path
    """
    for file_name in os.listdir(path):
        if file_name == 'scrapy.cfg':
            return SpiderType.SCRAPY


def get_spider_col_fields(col_name: str, task_id: str = None, limit: int = 100) -> list:
    """
    Get spider collection fields
    :param col_name: collection name
    :param task_id: task_id
    :param limit: limit
    """
    filter_ = {}
    if task_id is not None:
        filter_['task_id'] = task_id
    items = db_manager.list(col_name, filter_, limit=limit, sort_key='_id')
    fields = set()
    for item in items:
        for k in item.keys():
            fields.add(k)
    return list(fields)


def get_last_n_run_errors_count(spider_id: ObjectId, n: int) -> list:
    tasks = db_manager.list(col_name='tasks',
                            cond={'spider_id': spider_id},
                            sort_key='create_ts',
                            limit=n)
    count = 0
    for task in tasks:
        if task['status'] == TaskStatus.FAILURE:
            count += 1
    return count


def get_last_n_day_tasks_count(spider_id: ObjectId, n: int) -> list:
    return db_manager.count(col_name='tasks',
                            cond={
                                'spider_id': spider_id,
                                'create_ts': {
                                    '$gte': (datetime.now() - timedelta(n))
                                }
                            })


def get_list_page_data(spider, sel):
    data = []
    if spider['item_selector_type'] == QueryType.XPATH:
        items = sel.xpath(spider['item_selector'])
    else:
        items = sel.cssselect(spider['item_selector'])
    for item in items:
        row = {}
        for f in spider['fields']:
            if f['type'] == QueryType.CSS:
                # css selector
                res = item.cssselect(f['query'])
            else:
                # xpath
                res = item.xpath(f['query'])

            if len(res) > 0:
                if f['extract_type'] == ExtractType.TEXT:
                    row[f['name']] = res[0].text
                else:
                    row[f['name']] = res[0].get(f['attribute'])
        data.append(row)
    return data


def get_detail_page_data(url, spider, idx, data):
    r = requests.get(url)

    sel = etree.HTML(r.content)

    row = {}
    for f in spider['detail_fields']:
        if f['type'] == QueryType.CSS:
            # css selector
            res = sel.cssselect(f['query'])
        else:
            # xpath
            res = sel.xpath(f['query'])

        if len(res) > 0:
            if f['extract_type'] == ExtractType.TEXT:
                row[f['name']] = res[0].text
            else:
                row[f['name']] = res[0].get(f['attribute'])

    # assign values
    for k, v in row.items():
        data[idx][k] = v


def generate_urls(base_url: str) -> str:
    url = base_url

    # number range list
    list_arr = []
    for i, res in enumerate(re.findall(r'{(\d+),(\d+)}', base_url)):
        try:
            _min = int(res[0])
            _max = int(res[1])
        except ValueError as err:
            raise ValueError(f'{base_url} is not a valid URL pattern')

        # list
        _list = range(_min, _max + 1)

        # key
        _key = f'n{i}'

        # append list and key
        list_arr.append((_list, _key))

        # replace url placeholder with key
        url = url.replace('{' + res[0] + ',' + res[1] + '}', '{' + _key + '}', 1)

    # string list
    for i, res in enumerate(re.findall(r'\[([\w\-,]+)\]', base_url)):
        # list
        _list = res.split(',')

        # key
        _key = f's{i}'

        # append list and key
        list_arr.append((_list, _key))

        # replace url placeholder with key
        url = url.replace('[' + ','.join(_list) + ']', '{' + _key + '}', 1)

    # combine together
    _list_arr = []
    for res in itertools.product(*map(lambda x: x[0], list_arr)):
        _url = url
        for _arr, _rep in zip(list_arr, res):
            _list, _key = _arr
            _url = _url.replace('{' + _key + '}', str(_rep), 1)
        yield _url
