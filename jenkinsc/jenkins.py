import json
from datetime import datetime
from logging import getLogger
from operator import itemgetter
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
        self.url = '{}/job/{}'.format(url.rstrip('/'), job_name)
        self.auth = auth

    def build(self, build_params=None, block=False):
        response = self.trigger_build(build_params)
        qi = QueueItem(response.headers['Location'], self.auth)
        if block:
            qi.get_build().wait_till_completion()
        return qi

    @lost_connection_wrapper
    def trigger_build(self, build_params):
        url = '{}/{}'.format(self.url, ('buildWithParameters' if build_params else 'build'))
        data = transform_jenkins_params(build_params)
        data.update(build_params)
        logger.info('Building job: %s with parameters: %s', url, build_params)
        response = requests.post(url, data=data, auth=self.auth)
        if response.status_code not in [200, 201]:
            response.raise_for_status()
            raise JenkinsRequestError('failed to invoke jenkins job')
        return response

    def get_build(self, build_number):
        build = Build('{}/{}'.format(self.url, build_number), self.auth)
        build.pull_build_data()
        return build

    @lost_connection_wrapper
    def find_last_successful_build_by_display_name(self, display_name_part):
        url = '{}/api/json'.format(self.url)
        response = requests.get(url, auth=self.auth)
        if response.status_code not in [200, 201]:
            response.raise_for_status()
            raise JenkinsRequestError('failed to find job builds')
        for build_info in sorted(response.json()['builds'], key=itemgetter('number'), reverse=True):
            logger.info('getting build info: %s', build_info['number'])
            build = Build('{}/{}'.format(self.url, build_info['number']), self.auth)
            build.pull_build_data()
            if display_name_part in build.data['displayName'] and build.data['result'] == 'SUCCESS':
                return build


class QueueItem:
    def __init__(self, queue_item_url, auth):
        self.queue_item_url = queue_item_url.rstrip('/')
        self.auth = auth
        self.build = None

    def get_build(self):
        logger.info('Getting queue item build')
        while True:
            build = self.get_build_if_available()
            if build is None:
                logger.info('Waiting in the queue to start the build')
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
            try:
                if not qi_data['cancelled']:
                    self.build = Build(qi_data['executable']['url'], self.auth)
                    return self.build
                else:
                    raise CanceledBuild('The build is canceled')
            except Exception:
                logger.info('qi_data: %s', qi_data)
                raise


class Build:
    def __init__(self, url, auth):
        self.url = url.rstrip('/')
        self.auth = auth
        self.data = None

    def wait_till_completion(self):
        logger.info('Waiting till build completion')
        wait_start = datetime.now()
        while not self.ready():
            seconds_since_start = int((datetime.now() - wait_start).total_seconds())
            logger.info('Waited "%ssec" for "%s" build to finish', seconds_since_start,
                        self.data['fullDisplayName'])
            sleep(15)

    def ready(self):
        self.pull_build_data()
        return not self.data['building']

    @lost_connection_wrapper
    def pull_build_data(self):
        response = requests.get('{}/api/json'.format(self.url), auth=self.auth)
        if response.status_code in [200, 201]:
            self.data = response.json()
        else:
            response.raise_for_status()
            raise JenkinsRequestError('Failed on getting build data')

    def successful(self):
        self.pull_build_data()
        return self.data['result'] == 'SUCCESS'

    @lost_connection_wrapper
    def update_build_name(self, new_build_name):
        response = requests.post('{}/configSubmit'.format(self.url),
                                 data={'json': json.dumps({'displayName': new_build_name, 'description': ''})},
                                 auth=self.auth)
        if response.status_code not in [200, 201]:
            response.raise_for_status()
            raise JenkinsRequestError('Failed on getting build data')

    def get_params(self):
        if self.data is None:
            self.pull_build_data()
        for action in self.data['actions']:
            if 'parameters' in action:
                return {build_param['name']: build_param['value'] for build_param in action['parameters']}
