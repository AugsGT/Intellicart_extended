import decimal

from rest_framework.renderers import JSONRenderer
from rest_framework.utils.encoders import JSONEncoder


class DecimalAsStringEncoder(JSONEncoder):
    """Money must never travel as a float: 88.33 would become 88.3299999...
    Every Decimal in a response is sent as a string, like the serializers do."""

    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return str(obj)
        return super().default(obj)


class DecimalSafeJSONRenderer(JSONRenderer):
    encoder_class = DecimalAsStringEncoder
