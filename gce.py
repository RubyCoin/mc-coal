import fix_path

import datetime
import httplib2
import logging

from apiclient import discovery
from apiclient.errors import HttpError

from google.appengine.api import app_identity, memcache
from google.appengine.ext import ndb

from oauth2client.appengine import AppAssertionCredentials


GCE_SCOPE = 'https://www.googleapis.com/auth/compute'
API_VERSION = 'v1'
GCE_URL = 'https://www.googleapis.com/compute/%s/projects/' % (API_VERSION)
BOOT_IMAGE_URL = '%s%s/global/images/%s' % (GCE_URL, 'debian-cloud', 'debian-7-wheezy-v20140605')
SCOPES = [
    'https://www.googleapis.com/auth/devstorage.full_control',
    'https://www.googleapis.com/auth/compute',
    'https://www.googleapis.com/auth/taskqueue'
]
INSTANCE_NAME = 'coal-instance'
ADDRESS_NAME = 'coal-address'
FIREWALL_NAME = 'coal-firewall'
COAL_BOOT_DISK_NAME = 'coal-boot-disk'
COAL_DISK_NAME = 'coal-disk'
GCE_MAX_IDLE_SECONDS = 600  # 10 minutes


class Instance(ndb.Model):
    zone = ndb.StringProperty(required=False, default='us-central1-a')
    machine_type = ndb.StringProperty(required=False, default='g1-small')
    reserved_ip = ndb.BooleanProperty(required=False, default=False)
    disk_size = ndb.IntegerProperty(default=100)
    server_key = ndb.KeyProperty(default=None)
    idle = ndb.DateTimeProperty()
    created = ndb.DateTimeProperty(auto_now_add=True)
    updated = ndb.DateTimeProperty(auto_now=True)

    @property
    def name(self):
        return '{0}-{1}'.format(INSTANCE_NAME, self.key.id())

    @property
    def boot_disk_name(self):
        return '{0}-{1}-boot'.format(COAL_BOOT_DISK_NAME, self.key.id())

    @property
    def coal_disk_name(self):
        return '{0}-{1}'.format(COAL_DISK_NAME, self.key.id())

    def start(self):
        status = self.get_status()
        if status != 'UNPROVISIONED':
            logging.warning("Trying to start instance whose status is '{0}'".format(status))
            return
        project_id = get_project_id()
        project_url = '%s%s' % (GCE_URL, project_id)
        network_url = '%s/global/networks/%s' % (project_url, 'default')
        boot_disk_url = '%s/zones/%s/disks/%s' % (project_url, self.zone, self.boot_disk_name)
        coal_disk_url = '%s/zones/%s/disks/%s' % (project_url, self.zone, self.coal_disk_name)
        machine_type_url = '%s/zones/%s/machineTypes/%s' % (project_url, self.zone, self.machine_type)
        address = None
        if self.reserved_ip:
            region = get_region(self.zone)
            address = verify_address(region)
            if not address:
                address = create_address(region)
        verify_minecraft_firewall(network_url)
        if not verify_disk(self.boot_disk_name, self.zone):
            create_disk(self.boot_disk_name, self.zone, source=BOOT_IMAGE_URL)
        if not verify_disk(self.coal_disk_name, self.zone):
            create_disk(self.coal_disk_name, self.zone, size=self.disk_size)
        disks = [
            {'source': boot_disk_url, 'type': 'PERSISTENT', 'boot': True, 'autoDelete': False},
            {'source': coal_disk_url, 'type': 'PERSISTENT', 'boot': False, 'autoDelete': False, 'deviceName': 'coal'}
        ]
        access_configs = [{
            'type': 'ONE_TO_ONE_NAT',
            'name': 'External NAT'
        }]
        if address:
            access_configs[0]['natIP'] = address
        instance = {
            'name': self.name,
            'machineType': machine_type_url,
            'disks': disks,
            'networkInterfaces': [{
                'accessConfigs': access_configs,
                'network': network_url
            }],
            'serviceAccounts': [
                {
                    'email': 'default',
                    'scopes': SCOPES
                },
            ],
            'metadata': [{
                'items': [
                    {
                        'key': 'startup-script',
                        'value': open('gce-instance-startup.sh', 'r').read()
                    },
                    {
                        'key': 'project-id',
                        'value': project_id
                    },
                    {
                        'key': 'instance-name',
                        'value': self.name
                    }
                ]
            }]
        }
        execute_request(
            get_gce_service().instances().insert(
                project=project_id, body=instance, zone=self.zone
            )
        )
        self.idle = None
        self.put()

    def stop(self):
        if not self.is_running():
            return
        execute_request(
            get_gce_service().instances().delete(
                instance=self.name, project=get_project_id(), zone=self.zone
            )
        )
        self.idle = None
        self.put()

    def stop_if_idle(self):
        if not (self.is_running and self.idle):
            return
        if datetime.datetime.utcnow() > self.idle + datetime.timedelta(seconds=GCE_MAX_IDLE_SECONDS):
            self.stop()

    def is_setup(self):
        return self.get_status() is not None

    def is_unprovisioned(self):
        return self.get_status() == 'UNPROVISIONED'

    def is_running(self):
        return self.get_status() == 'RUNNING'

    def get_region(self):
        try:
            zone = execute_request(
                get_gce_service().zones().get(project=get_project_id(), zone=self.zone)
            )
            region = zone['region']
            region = region.split('/')[-1]
            return region
        except HttpError:
            pass
        return None

    def get_instance(self):
        instance = None
        try:
            instance = execute_request(
                get_gce_service().instances().get(
                    instance=self.name, project=get_project_id(), zone=self.zone
                )
            )
        except HttpError as e:
            if e.resp.status != 404:
                raise
        return instance

    def get_status(self):
        status = None
        try:
            instance = execute_request(
                get_gce_service().instances().get(
                    instance=self.name, project=get_project_id(), zone=self.zone
                )
            )
            if instance is not None:
                status = instance['status']
        except HttpError as e:
            if e.resp.status == 404:
                status = 'UNPROVISIONED'
            elif e.resp.status != 401:
                raise
        return status

    def get_address(self):
        address = None
        instance = self.get_instance()
        if instance is not None:
            interface = instance['networkInterfaces']
            if interface:
                configs = interface['accessConfigs']
                if configs:
                    address = configs['natIP']
        return address

    @classmethod
    def singleton(cls):
        return cls.get_or_insert('singleton')


def get_project_id():
    return app_identity.get_application_id()


def get_gce_service():
    credentials = AppAssertionCredentials(scope=GCE_SCOPE)
    http = credentials.authorize(httplib2.Http(memcache, 30))
    return discovery.build('compute', API_VERSION, http=http)


def execute_request(request, block=False):
    try:
        response = request.execute()
        if block:
            gce_service = get_gce_service()
            status = response['status']
            while status != 'DONE' and response:
                operation_id = response['name']
                if 'zone' in response:
                    zone_name = response['zone'].split('/')[-1]
                    status_request = gce_service.zoneOperations().get(
                        project=get_project_id(),
                        operation=operation_id,
                        zone=zone_name
                    )
                else:
                    status_request = gce_service.globalOperations().get(
                        project=get_project_id(), operation=operation_id
                    )
                response = status_request.execute()
                if response:
                    status = response['status']
    except HttpError as e:
        if e.resp.status != 404 and e.resp.status != 401:
            logging.error("Error ({0}) calling {1}".format(e.resp, getattr(e, 'operationType', None)))
        raise
    return response


def verify_address(region):
    try:
        address = None
        while not address:
            response = execute_request(
                get_gce_service().addresses().get(project=get_project_id(), region=region, address=ADDRESS_NAME)
            )
            if response['status'] == 'RESERVED':
                address = response.get('address', None)
        return address
    except HttpError:
        pass
    return None


def create_address(region):
    execute_request(
        get_gce_service().addresses().insert(project=get_project_id(), region=region, body={'name': ADDRESS_NAME})
    )
    address = None
    while not address:
        response = execute_request(
            get_gce_service().addresses().get(project=get_project_id(), region=region, address=ADDRESS_NAME)
        )
        if response['status'] == 'RESERVED':
            address = response.get('address', None)
    return address


def verify_minecraft_firewall(network):
    try:
        execute_request(get_gce_service().firewalls().get(firewall=FIREWALL_NAME, project=get_project_id()))
    except HttpError as e:
        if e.resp.status == 404:
            create_minecraft_firewall(network)
        else:
            raise


def create_minecraft_firewall(network):
    project_id = get_project_id()
    firewall = {
        'name': FIREWALL_NAME,
        'sourceRanges': ["0.0.0.0/0"],
        'allowed': [{
            'IPProtocol': 'tcp',
            'ports': [i for i in range(25565, 25575)]
        }],
        'network': network
    }
    execute_request(
        get_gce_service().firewalls().insert(project=project_id, body=firewall)
    )


def verify_disk(name, zone, size=None):
    try:
        disk = execute_request(
            get_gce_service().disks().get(
                disk=name, project=get_project_id(), zone=zone
            )
        )
        if size is not None:
            try:
                existing_size = int(disk['sizeGb'])
            except:
                existing_size = 0
            if existing_size != size:
                logging.info("New disk size for '{0}' ({1} GB). Removing previous ({2} GB)...".format(
                    name, size, existing_size
                ))
                delete_disk(name, zone)
                return False
        return True
    except HttpError as e:
        if e.resp.status != 404:
            logging.error("Error verifying disk (name: {0}, zone: {1}, size: {2}): {3}".format(
                name, zone, size, e
            ))
    return False


def create_disk(name, zone, source=None, size=None):
    body = {'name': name}
    if size is not None:
        body['sizeGb'] = size
    kwargs = {'project': get_project_id(), 'zone': zone, 'body': body}
    if source is not None:
        kwargs['sourceImage'] = source
    execute_request(
        get_gce_service().disks().insert(**kwargs)
    )


def delete_disk(name, zone):
    try:
        execute_request(
            get_gce_service().disks().delete(disk=name, project=get_project_id(), zone=zone)
        )
        return True
    except HttpError as e:
        logging.error("Error deleting disk (name: {0}, zone: {1}): {2}".format(name, zone, e))
    return False


def get_zones():
    try:
        request = get_gce_service().zones().list(project=get_project_id())
        response = request.execute()
        if response and 'items' in response:
            return [zone['name'] for zone in response['items']]
    except HttpError as e:
        logging.error("Error ({0}) getting zones".format(e.resp))
        if e.resp.status != 404 and e.resp.status != 401:
            raise
    return None


def get_region(zone):
    try:
        zone = execute_request(
            get_gce_service().zones().get(project=get_project_id(), zone=zone)
        )
        region = zone['region']
        region = region.split('/')[-1]
        return region
    except HttpError:
        pass
    return None


def is_setup():
    setup = False
    try:
        request = get_gce_service().zones().list(project=get_project_id())
        request.execute()
        setup = True
    except HttpError as e:
        logging.error("GCE not set up: {0}".format(e))
        if e.resp.status != 404 and e.resp.status != 401:
            raise
    return setup
