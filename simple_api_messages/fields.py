from postman.fields import CommaSeparatedUserField
from rest_framework.fields import CharField
from rest_framework import serializers

from simple_api_messages.models import *

from simple_api_messages.serializers import *


class MyCharField(CharField):

    def __init__(self, *args, **kwargs):
        # print 'MyCharField kwargs:', kwargs
        # kwargs.pop('max', None) # causing got an unexpected keyword argument 'max'
        super(MyCharField, self).__init__(**kwargs)


class MyCommaSeparatedUserField(CommaSeparatedUserField):

    def __init__(self, *args, **kwargs):
        super(MyCommaSeparatedUserField, self).__init__(*args, **kwargs)

    def set_max(self, max):
        pass


class CommaSeparatedRecipientField(MyCharField, MyCommaSeparatedUserField):
    min = 1 # min number recipient
    max = 10 # max number recipient
    user_filter = None

    def __init__(self, *args, **kwargs):
        # print 'CommaSeparatedRecipientField kwargs:', kwargs
        max_recipient = kwargs.pop('max', None)
        if max_recipient:
            self.max = max_recipient

        super(CommaSeparatedRecipientField, self).__init__(*args, **kwargs)

    def to_representation(self, obj):
        # print 'to_representation obj:', obj
        return obj

    def to_internal_value(self, data):
        cleaned_recipients = self.clean(data)
        recipient_list = [_.email for _ in cleaned_recipients]
        # print 'to_internal_value recipient_list:', cleaned_recipients
        return recipient_list
