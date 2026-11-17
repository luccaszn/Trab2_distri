"""Function URL entrypoint; shared logic lives in the sebo-common layer."""
from sebo_common import handle


def lambda_handler(event, context):
    return handle('solicitar', event, context)
