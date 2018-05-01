import json
from datetime import datetime
from functools import lru_cache
from logging import getLogger
from operator import itemgetter
from time import sleep

import requests
from requests.auth import HTTPBasicAuth

from jenkinsc.utils import transform_jenkins_params, lost_connection_wrapper, find_full_string_by_its_part

logger = getLogger('jenkinsc')


class CanceledBuild(Exception):
    pass


class JenkinsRequestError(Exception):
    pass


class Jenkins:
    def __init__(self, url, username, password):
        self.url = url
        self.auth = HTTPBasicAuth(username, password)

    @lru_cache()
    def __getitem__(self, item):
        jobs = self.get_all_jobs()
        name = find_full_string_by_its_part(item, jobs)
        if name is not None:
            return JenkinsJob(name, self.url, self.auth)
        else:
            raise Exception('Cannot find any job to match the pattern: {}'.format(item))

    @lost_connection_wrapper
    def get_all_jobs(self):
        url = '{}/api/json'.format(self.url)
        response = requests.post(url, auth=self.auth)
        if response.status_code not in [200, 201]:
            response.raise_for_status()
            raise JenkinsRequestError('failed to invoke jenkins job')
        return sorted([job['name'] for job in response.json()['jobs']])


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
        logger.info('Building job: %s with parameters: %s', url, build_params)
        job_param_names = self.get_params()
        if build_params:
            if isinstance(build_params, dict):
                build_params = {find_full_string_by_its_part(name, job_param_names): value for name, value in build_params.items()}
            else:
                build_params = {name: value for name, value in zip(job_param_names, build_params)}
            data = transform_jenkins_params(build_params)
            data.update(build_params)
        else:
            data = None
        response = requests.post(url, data=data, auth=self.auth)
        if response.status_code not in [200, 201]:
            response.raise_for_status()
            raise JenkinsRequestError('failed to invoke jenkins job')
        return response

    def get_params(self):
        url = '{}/api/json'.format(self.url)
        response = requests.post(url, auth=self.auth)
        if response.status_code not in [200, 201]:
            response.raise_for_status()
            raise JenkinsRequestError('failed to get jenkins job parameters')
        job_params = []
        for action in response.json()['actions']:
            if 'parameterDefinitions' in action:
                for param in action['parameterDefinitions']:
                    job_params.append(param['name'])
        return job_params

    def get_build(self, build_number):
        build = Build('{}/{}'.format(self.url, build_number), self.auth)
        build.pull_build_data()
        return build

    @lost_connection_wrapper
    def find_last_successful_build_by_display_name(self, display_name_part):
        url = '{}/api/json?tree=allBuilds[number,displayName,result]'.format(self.url)
        response = requests.get(url, auth=self.auth)
        if response.status_code not in [200, 201]:
            response.raise_for_status()
            raise JenkinsRequestError('failed to find job builds')
        for build_info in sorted(response.json()['allBuilds'], key=itemgetter('number'), reverse=True):
            logger.info('getting build info: %s', build_info['number'])
            if display_name_part in build_info.data['displayName'] and build_info.data['result'] == 'SUCCESS':
                return Build('{}/{}'.format(self.url, build_info['number']), self.auth)


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

    def get_build_if_available(self):
        if self.build is not None:
            return self.build
        qi_data = self.get_qi_data()
        if not qi_data['blocked']:
            try:
                if not qi_data['cancelled']:
                    self.build = Build(qi_data['executable']['url'], self.auth)
                    return self.build
                else:
                    raise CanceledBuild('The build is canceled')
            except Exception:
                logger.warning('error encountered on getting the build url, retrying.')
                logger.info('qi_data_url: %s', '{}/api/json'.format(self.queue_item_url))
                logger.info('qi_data: %s', qi_data)
                for retry_attempt in range(5):
                    sleep(60)
                    qi_data = self.get_qi_data()
                    try:
                        if not qi_data['cancelled']:
                            self.build = Build(qi_data['executable']['url'], self.auth)
                            return self.build
                        else:
                            raise CanceledBuild('The build is canceled')
                    except CanceledBuild:
                        raise
                    except Exception:
                        pass
                raise

    @lost_connection_wrapper
    def get_qi_data(self):
        response = requests.get('{}/api/json'.format(self.queue_item_url), auth=self.auth)
        if response.status_code not in [200, 201]:
            response.raise_for_status()
            raise JenkinsRequestError('Failed to get queue item information')
        return response.json()


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
