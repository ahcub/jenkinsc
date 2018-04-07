import json
from logging import getLogger
from time import sleep

import requests
from requests import HTTPError
from requests.auth import HTTPBasicAuth

logger = getLogger()


class CanceledBuild(Exception):
    pass


class Jenkins:
    def __init__(self, url, username, password):
        self.url = url
        self.auth = HTTPBasicAuth(username, password)

    def __getitem__(self, item):
        return JenkinsJob(item, self.url, self.auth)


class JenkinsJob:
    def __init__(self, job_name, url, auth):
        self.job_name = job_name
        self.url = url
        self.auth = auth

    def build(self, build_params=None, block=False):
        url = '{}/job/{}/{}'.format(self.url, self.job_name, ('buildWithParameters' if build_params else 'build'))

        result = requests.post(url, data=transform_jenkins_params(build_params), auth=self.auth)
        if result.status_code in [200, 201]:
            qi = QueueItem(result.headers['Location'], self.auth)
            if block:
                qi.get_build().wait_till_completion()
            return qi
        else:
            raise HTTPError('failed to invoke jenkins job')


class Build:
    def __init__(self, build_url, auth):
        self.build_url = build_url
        self.auth = auth

    def wait_till_completion(self):
        while True:
            build_info = requests.get('{}/api/json'.format(self.build_url), auth=self.auth)
            if build_info.status_code in [200, 201]:
                build_data = build_info.json()
                logger.info('waiting for build to finish')
                if not build_data['building']:
                    return build_data['result']
                sleep(15)
            else:
                raise HTTPError('Failed on getting build data')

    def is_successful(self):
        build_info = requests.get('{}/api/json'.format(self.build_url), auth=self.auth)
        if build_info.status_code in [200, 201]:
            build_data = build_info.json()
            return build_data['result'] == 'SUCCESS'
        else:
            raise HTTPError('Failed on getting build data')


class QueueItem:
    def __init__(self, queue_item_url, auth):
        self.queue_item_url = queue_item_url
        self.auth = auth
        self.build = None

    def get_build(self):
        if self.build is not None:
            return self.build
        while True:
            qi_info = requests.get('{}/api/json'.format(self.queue_item_url), auth=self.auth)
            if qi_info.status_code not in [200, 201]:
                raise HTTPError('Failed to get queue item information')
            qi_data = qi_info.json()
            if qi_data['blocked']:
                logger.info('build is waiting in the queue')
                sleep(10)
                continue
            else:
                if not qi_data['cancelled']:
                    self.build = Build(qi_data['executable']['url'], self.auth)
                    return self.build
                else:
                    raise CanceledBuild('The build is canceled')


def transform_jenkins_params(params):
    result_params = []
    for name, value in params.items():
        result_params.append({'name': name, 'value': value})
    if len(result_params) == 1:
        result_params = result_params[0]
    return {'json': json.dumps({'parameter': result_params})}
