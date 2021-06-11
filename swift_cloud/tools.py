import logging
import requests

log = logging.getLogger(__name__)


class SwiftCloudTools:

    def __init__(self, conf):
        self.api_token = conf.get('tools_api_token')
        self.api_url = conf.get('tools_api_url')
        self.expirer_url = self.api_url + '/v1/expirer/'

    def add_delete_at(self, account, container, obj, date):
        try:
            res = requests.post(self.expirer_url,
                data={
                    'account': account,
                    'container': container,
                    'object': obj,
                    'date': date
                },
                headers={
                    'Content-Type': 'application/json',
                    'X-Auth-Token': self.api_token
                })
            return True, res.text()
        except Exception as err:
            log.error(err)
            return False, str(err)

    def remove_delete_at(self, account, container, obj):
        try:
            res = requests.delete(self.expirer_url,
                data={
                    'account': account,
                    'container': container,
                    'object': obj
                },
                headers={
                    'Content-Type': 'application/json',
                    'X-Auth-Token': self.api_token
                })
            return True, res.text()
        except Exception as err:
            log.error(err)
            return False, str(err)
