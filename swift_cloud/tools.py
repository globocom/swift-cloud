import logging
import requests
import json

from datetime import datetime

log = logging.getLogger(__name__)


class SwiftCloudTools:

    def __init__(self, conf):
        self.api_token = conf.get('tools_api_token')
        self.api_url = conf.get('tools_api_url')
        self.expirer_url = self.api_url + '/v1/expirer/'
        self.container_info_url = self.api_url + '/v1/container-info/'

    def add_delete_at(self, account, container, obj, date):
        try:
            res = requests.post(self.expirer_url,
                data=json.dumps({
                    'account': account,
                    'container': container,
                    'object': obj,
                    'date': date
                }),
                headers={
                    'Content-Type': 'application/json',
                    'X-Auth-Token': self.api_token
                })
            return True, res.text
        except Exception as err:
            log.error(err)
            return False, str(err)

    def remove_delete_at(self, account, container, obj):
        try:
            res = requests.delete(self.expirer_url,
                data=json.dumps({
                    'account': account,
                    'container': container,
                    'object': obj
                }),
                headers={
                    'Content-Type': 'application/json',
                    'X-Auth-Token': self.api_token
                })
            return True, res.text
        except Exception as err:
            log.error(err)
            return False, str(err)

    def convert_timestamp_to_datetime(self, timestamp):
        try:
            date_time = datetime.fromtimestamp(int(timestamp))
            return True, date_time.strftime('%Y-%m-%d %H:%M:%S')
        except Exception as err:
            log.error(err)
            return False, str(err)
