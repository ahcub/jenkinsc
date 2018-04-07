from logging import getLogger
from time import sleep

import requests
from requests.auth import HTTPBasicAuth

from jenkinsc.utils import transform_jenkins_params, lost_connection_wrapper

logger = getLogger('jenkinsc')


class CanceledBuild(Exception):
    pass


class JenkinsRequestError(Exception):
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
        response = self.trigger_build(build_params)
        qi = QueueItem(response.headers['Location'], self.auth)
        if block:
            qi.get_build().wait_till_completion()
        return qi

    @lost_connection_wrapper
    def trigger_build(self, build_params):
        url = '{}/job/{}/{}'.format(self.url, self.job_name, ('buildWithParameters' if build_params else 'build'))
        response = requests.post(url, data=transform_jenkins_params(build_params), auth=self.auth)
        if response.status_code not in [200, 201]:
            response.raise_for_status()
            raise JenkinsRequestError('failed to invoke jenkins job')
        return response


class QueueItem:
    def __init__(self, queue_item_url, auth):
        self.queue_item_url = queue_item_url
        self.auth = auth
        self.build = None

    def get_build(self):
        while True:
            build = self.get_build_if_available()
            if build is None:
                logger.info('build is waiting in the queue')
                sleep(10)
            else:
                return build

    @lost_connection_wrapper
    def get_build_if_available(self):
        if self.build is not None:
            return self.build
        response = requests.get('{}/api/json'.format(self.queue_item_url), auth=self.auth)
        if response.status_code not in [200, 201]:
            response.raise_for_status()
            raise JenkinsRequestError('Failed to get queue item information')
        qi_data = response.json()
        if not qi_data['blocked']:
            if not qi_data['cancelled']:
                self.build = Build(qi_data['executable']['url'], self.auth)
                return self.build
            else:
                raise CanceledBuild('The build is canceled')


class Build:
    def __init__(self, build_url, auth):
        self.build_url = build_url
        self.auth = auth

    def wait_till_completion(self):
        while True:
            if not self.ready():
                logger.info('waiting for build to finish')
                sleep(15)

    @lost_connection_wrapper
    def ready(self):
        response = requests.get('{}/api/json'.format(self.build_url), auth=self.auth)
        if response.status_code in [200, 201]:
            return not response.json()['building']
        else:
            response.raise_for_status()
            raise JenkinsRequestError('Failed on getting build data')

    @lost_connection_wrapper
    def successful(self):
        response = requests.get('{}/api/json'.format(self.build_url), auth=self.auth)
        if response.status_code in [200, 201]:
            build_data = response.json()
            return build_data['result'] == 'SUCCESS'
        else:
            response.raise_for_status()
            raise JenkinsRequestError('Failed on getting build data')
