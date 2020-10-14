# (C) Datadog, Inc. 2020-present
# All rights reserved
# Licensed under a 3-clause BSD style license (see LICENSE)
import logging
import os
import ssl
from typing import TYPE_CHECKING, Any, AnyStr, Dict

from six import iteritems

from ..config import is_affirmative

if TYPE_CHECKING:
    from ..types import InstanceType

LOGGER = logging.getLogger(__file__)

STANDARD_FIELDS = {
    'tls_verify': True,
    'tls_ca_cert': None,
    'tls_cert': None,
    'tls_private_key': None,
    'tls_private_key_password': None,
    'validate_hostname': True,
}


class TlsContextWrapper(object):
    __slots__ = ('logger', 'config', 'tls_context')

    def __init__(self, instance, remapper=None):
        # type: (InstanceType, Dict[AnyStr, Dict[AnyStr, Any]]) -> None
        default_fields = dict(STANDARD_FIELDS)

        # Populate with the default values
        config = {field: instance.get(field, value) for field, value in iteritems(default_fields)}

        if remapper is None:
            remapper = {}

        for remapped_field, data in iteritems(remapper):
            field = data.get('name')

            # Ignore fields we don't recognize
            if field not in STANDARD_FIELDS:
                continue

            # Ignore remapped fields if the standard one is already used
            if field in instance:
                continue

            # Invert default booleans if need be
            default = default_fields[field]
            if data.get('invert'):
                default = not default

            # Get value, with a possible default
            value = instance.get(remapped_field, data.get('default', default))

            # Invert booleans if need be
            if data.get('invert'):
                value = not is_affirmative(value)

            config[field] = value

        if any(
            (config['tls_ca_cert'], config['tls_cert'], config['tls_private_key'], config['tls_private_key_password'])
        ):
            config['tls_verify'] = True

        self.config = config
        self.tls_context = self._create_tls_context()

    def _create_tls_context(self):
        # type: () -> ssl.SSLContext

        # https://docs.python.org/3/library/ssl.html#ssl.SSLContext
        # https://docs.python.org/3/library/ssl.html#ssl.PROTOCOL_TLS
        context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS)

        # https://docs.python.org/3/library/ssl.html#ssl.SSLContext.verify_mode
        if not self.config['tls_verify']:
            context.verify_mode = ssl.CERT_NONE
            return context
        context.verify_mode = ssl.CERT_REQUIRED

        # https://docs.python.org/3/library/ssl.html#ssl.SSLContext.check_hostname
        context.check_hostname = self.config['validate_hostname']

        # https://docs.python.org/3/library/ssl.html#ssl.SSLContext.load_verify_locations
        # https://docs.python.org/3/library/ssl.html#ssl.SSLContext.load_default_certs
        ca_cert = self.config['tls_ca_cert']
        if not ca_cert:
            context.load_default_certs(ssl.Purpose.SERVER_AUTH)
        else:
            ca_cert = os.path.expanduser(ca_cert)
            if os.path.isdir(ca_cert):
                context.load_verify_locations(cafile=None, capath=ca_cert, cadata=None)
            else:
                context.load_verify_locations(cafile=ca_cert, capath=None, cadata=None)

        # https://docs.python.org/3/library/ssl.html#ssl.SSLContext.load_cert_chain
        client_cert, client_key = self.config['tls_cert'], self.config['tls_private_key']
        client_key_pass = self.config['tls_private_key_password']
        if client_key:
            client_key = os.path.expanduser(client_key)
        if client_cert:
            client_cert = os.path.expanduser(client_cert)
            context.load_cert_chain(client_cert, keyfile=client_key, password=client_key_pass)

        return context

    def refresh_tls_context(self):
        # type: () -> None
        self.tls_context = self._create_tls_context()
