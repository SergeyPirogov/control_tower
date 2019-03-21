#  Copyright (c) 2018 getcarrier.io
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import argparse

from copy import deepcopy
from json import loads
from os import environ, path
from celery import Celery, group
from celery.result import GroupResult
from celery.contrib.abortable import AbortableAsyncResult
from celery.task.control import inspect
from time import sleep
from control_tower.drivers.redis_file import RedisFile

REDIS_USER = environ.get('REDIS_USER', '')
REDIS_PASSWORD = environ.get('REDIS_PASSWORD', 'password')
REDIS_HOST = environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = environ.get('REDIS_PORT', '6379')
REDIS_DB = environ.get('REDIS_DB', 1)


def str2bool(v):
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


def str2json(v):
    try:
        return loads(v)
    except:
        raise argparse.ArgumentTypeError('Json is not properly formatted.')


def arg_parse():
    parser = argparse.ArgumentParser(description='Carrier Command Center')
    parser.add_argument('-c', '--container', type=str,
                        help="Name of container to run the job e.g. getcarrier/dusty:latest")
    parser.add_argument('-e', '--execution_params', type=str2json,
                        help="Execution params for jobs e.g. \n"
                             "{\n\t'host': 'localhost', \n\t'port':'443', \n\t'protocol':'https'"
                             ", \n\t'project_name':'MY_PET', \n\t'environment':'stag', \n\t"
                             "'test_type': 'basic'"
                             "\n} will be valid for dast container")
    parser.add_argument('-t', '--job_type', type=str,
                        help="Type of a job: e.g. sast, dast, perf-jmeter, perf-ui")
    parser.add_argument('-n', '--job_name', type=str,
                        help="Name of a job (e.g. unique job ID, like %JOBNAME%_%JOBID%)")
    parser.add_argument('-q', '--concurrency', type=int, default=1,
                        help="Number of parallel workers to run the job")
    return parser.parse_args()


def parse_id():
    parser = argparse.ArgumentParser(description='Carrier Command Center')
    parser.add_argument('-g', '--groupid', type=str, default="", help="ID of the group for a task")
    parser.add_argument('-c', '--container', type=str, help="Name of container to run the job "
                                                            "e.g. getcarrier/dusty:latest")
    parser.add_argument('-t', '--job_type', type=str, help="Type of a job: e.g. sast, dast, perf-jmeter, perf-ui")
    parser.add_argument('-n', '--job_name', type=str, help="Name of a job (e.g. unique job ID, like %JOBNAME%_%JOBID%)")

    return parser.parse_args()


def connect_to_celery(concurrency):
    app = Celery('CarrierExecutor',
                 broker=f'redis://{REDIS_USER}:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}',
                 backend=f'redis://{REDIS_USER}:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}',
                 include=['celery'])
    if concurrency:
        workers = sum(value['pool']['max-concurrency'] for key, value in app.control.inspect().stats().items())
        active = sum(len(value) for key, value in app.control.inspect().active().items())
        available = workers - active
        print(f"Total Workers: {workers}")
        print(f"Available Workers: {available}")
        if workers < concurrency:
            print(f"We are unable to process your request due to limited resources. We have {workers} available")
            exit(1)
    return app


def start_job(args=None):
    if not args:
        args = arg_parse()
    app = connect_to_celery(args.concurrency)
    job_id_number = [ord(char) for char in f'{args.job_type}{args.container}{args.job_name}']
    job_id_number = int(sum(job_id_number)/len(job_id_number))
    callback_connection = f'redis://{REDIS_USER}:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{job_id_number}'
    tasks = []
    for _ in range(args.concurrency):
        exec_params = deepcopy(args.execution_params)
        if exec_params.get('jmeter_execution_string'):  # TODO: should be by pefmeter jobtype
            print("WARNING: you are using obsolete functionality")
            exec_params['jmeter_execution_string'] += f" -Jlg.id={args.job_name}_{_}"
        tasks.append(app.signature('tasks.execute',
                                   kwargs={'job_type': args.job_type,
                                           'container': args.container,
                                           'execution_params': exec_params,
                                           'redis_connection': callback_connection,
                                           'job_name': args.job_name}))
    task_group = group(tasks, app=app)
    group_id = task_group.apply_async()
    group_id.save()
    with open("_taskid", "w") as f:
        f.write(group_id.id)
    print(f"Group ID: {group_id.id}")
    exit(0)


def track_job(args=None, group_id=None):
    if not args:
        args = parse_id()
    if not group_id:
        group_id = args.groupid
    app = connect_to_celery(0)
    result = GroupResult.restore(group_id, app=app)
    while not result.ready():
        sleep(30)
        print("Still processing ... ")
    if result.successful():
        # TODO: add pulling results from redis
        print("We are done successfully")
    else:
        print("We are failed badly")
    for each in result.get():
        print(each)
    job_id_number = [ord(char) for char in f'{args.job_type}{args.container}{args.job_name}']
    job_id_number = int(sum(job_id_number) / len(job_id_number))
    callback_connection = f'redis://{REDIS_USER}:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{job_id_number}'
    redis_ = RedisFile(callback_connection)
    for document in redis_.client.scan_iter():
        redis_.get_key(path.join('/tmp/reports', document))
    exit(0)


def start_and_track():
    group_id = start_job()
    track_job(group_id=group_id)


def kill_job(args=None, group_id=None):
    if not args:
        args = parse_id()
    if not group_id:
        group_id = args.groupid
    if not group_id:
        with open("_taskid", "r") as f:
            group_id = f.read().strip()
    print(group_id)
    app = connect_to_celery(None)
    result = GroupResult.restore(group_id, app=app)
    tasks_id = []
    if not result.ready():
        abortable_result = []
        for task in result.children:
            tasks_id.append(tasks_id)
            abortable_id = AbortableAsyncResult(id=task.id, parent=result.id, app=app)
            abortable_id.abort()
            abortable_result.append(abortable_id)
        if abortable_result:
            while not all(res.result for res in abortable_result):
                sleep(5)
                print("Aborting distributed tasks ... ")
        print("Group aborted ...")
        print("Verifying that tasks aborted as well ... ")
        # This process is to handle a case when parent is canceled, but child have not
        i = inspect()
        tasks_list = []
        for tasks in [i.active(), i.scheduled(), i.reserved()]:
            for node in tasks:
                if tasks[node]:
                    tasks_list.append(task['id'] for task in tasks[node])
        abortable_result = []
        for task_id in tasks_id:
            if task_id in tasks_list:
                abortable_id = AbortableAsyncResult(id=task_id, app=app)
                abortable_id.abort()
                abortable_result.append(abortable_id)
        if abortable_result:
            while not all(res.result for res in abortable_result):
                sleep(5)
                print("Aborting distributed tasks ... ")
    exit(0)


if __name__ == "__main__":
    from control_tower.config_mock import Config
    config = Config()
    # group_id = start_job(config)
    config.groupid = '126ea08e-9bc5-432b-8118-fae0181cebbf'
    # sleep(10)
    kill_job(config)

