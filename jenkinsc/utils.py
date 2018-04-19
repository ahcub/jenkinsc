import json
from logging import getLogger
from time import sleep

from requests import ConnectTimeout, ConnectionError, HTTPError
from requests.packages.urllib3.exceptions import ReadTimeoutError

logger = getLogger('jenkinsc.utils')


def transform_jenkins_params(params):
    result_params = []
    for name, value in params.items():
        result_params.append({'name': name, 'value': value})
    if len(result_params) == 1:
        result_params = result_params[0]
    return {'json': json.dumps({'parameter': result_params})}


def lost_connection_wrapper(func):
    def wrapper(*args, **kwargs):
        for n in range(5):
            try:
                return func(*args, **kwargs)
            except (ConnectTimeout, ReadTimeoutError, ConnectionError):
                if n == 4:
                    raise
                logger.info('connection dropped, retrying in 15 sec')
                sleep(15)
            except HTTPError as err:
                if n == 4 or err.response.status_code not in [504, 401]:
                    raise
                if err.response.status_code == 504:
                    logger.exception('Jenkins failed with gateway timeout')
                if err.response.status_code == 401:
                    logger.exception('Jenkins failed with auth error')
                sleep(60)
    return wrapper


def find_full_string_by_its_part(string_part, full_strings):
    strings_that_fit_the_pattern_vs_weights = []
    for full_string in full_strings:
        full_string_index = 0
        for letter in string_part:
            index = find(full_string, letter, full_string_index)
            if index == -1:
                break
            else:
                full_string_index = index + 1
        else:
            strings_that_fit_the_pattern_vs_weights.append((len(full_string) - len(string_part), full_string))
    if strings_that_fit_the_pattern_vs_weights:
        return sorted(strings_that_fit_the_pattern_vs_weights)[0][1]
    else:
        raise Exception('Cannot find the full name by pattern: %s', string_part)


def find(full_string, letter, full_string_index):
    original_case = full_string.find(letter, full_string_index)
    inverted_case = full_string.find(letter.lower() if letter.isupper() else letter.upper(), full_string_index)
    if original_case == -1:
        return inverted_case
    if inverted_case == -1:
        return original_case

    return min(original_case, inverted_case)