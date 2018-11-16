from django.contrib.auth.models import User, Group
from rest_framework import serializers
from postman.models import Message as DmMessage, get_user_name, STATUS_ACCEPTED
from postman.utils import format_subject, format_body
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction, models as dbmodels
from .fields import CommaSeparatedRecipientField


class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = ('url', 'username', 'email', 'groups')


class GroupSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Group
        fields = ('url', 'name')

class UserWithPrivacySerializer(serializers.HyperlinkedModelSerializer):

    photo_thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = ('id', 'photo_thumbnail')


class DmMessageSerializer(serializers.ModelSerializer):
    datetime_format = "%d %b %Y %H:%M"

    sender = UserWithPrivacySerializer(read_only=True)
    recipient = UserWithPrivacySerializer(read_only=True)
    sent_at = serializers.DateTimeField(format=datetime_format)
    read_at = serializers.DateTimeField(format=datetime_format)
    replied_at = serializers.DateTimeField(format=datetime_format)
    sender_deleted_at = serializers.DateTimeField(format=datetime_format)
    recipient_deleted_at = serializers.DateTimeField(format=datetime_format)

    class Meta:
        model = DmMessage
        exclude = ('moderation_status', 'moderation_by', 'moderation_date', 'moderation_reason')


class BaseWriteSerializer(serializers.ModelSerializer):
    """The base write class for message serializer."""
    body = serializers.CharField(allow_blank=False)

    def __init__(self, *args, **kwargs):
        sender = kwargs.pop('sender', None)
        exchange_filter = kwargs.pop('exchange_filter', None)
        user_filter = kwargs.pop('user_filter', None)
        max = kwargs.pop('max', None)
        channel = kwargs.pop('channel', None)
        self.site = kwargs.pop('site', None)
        super(BaseWriteSerializer, self).__init__(*args, **kwargs)

        self.sender = sender if (sender and sender.is_authenticated()) else None
        if exchange_filter:
            self.exchange_filter = exchange_filter
        if 'recipients' in self.fields:
            if user_filter and hasattr(self.fields['recipients'], 'user_filter'):
                self.fields['recipients'].user_filter = user_filter

            if getattr(settings, 'POSTMAN_DISALLOW_MULTIRECIPIENTS', False):
                max = 1
            if max is not None and hasattr(self.fields['recipients'], 'set_max') \
                    and getattr(self, 'can_overwrite_limits', True):
                self.fields['recipients'].set_max(max)

            if channel and hasattr(self.fields['recipients'], 'set_arg'):
                self.fields['recipients'].set_arg(channel)

        error_messages = {
            'filtered': _("Writing to some users is not possible: {users}."),
            'filtered_user': _("{username}"),
            'filtered_user_with_reason': _("{username} ({reason})"),
        }

    def clean_recipients(self):
        raise serializers.ValidationError(['error '])

        """Check no filter prohibits the exchange."""
        recipients = self.cleaned_data['recipients']
        exchange_filter = getattr(self, 'exchange_filter', None)
        if exchange_filter:
            errors = []
            filtered_names = []
            recipients_list = recipients[:]
            for u in recipients_list:
                try:
                    reason = exchange_filter(self.sender, u, recipients_list)
                    if reason is not None:
                        recipients.remove(u)
                        filtered_names.append(
                            self.error_messages[
                                'filtered_user_with_reason' if reason else 'filtered_user'
                            ].format(username=get_user_name(u), reason=reason)
                        )
                except serializers.ValidationError as e:
                    recipients.remove(u)
                    errors.extend(e.messages)
            if filtered_names:
                errors.append(self.error_messages['filtered'].format(users=', '.join(filtered_names)))
            if errors:
                raise serializers.ValidationError(errors)
        return recipients

    def create(self, validated_data, recipient=None, parent=None, reply_all=None, auto_moderators=[]):
        """
        Save as many messages as there are recipients.

        Additional actions:
        - If it's a reply, build a conversation
        - Call auto-moderators
        - Notify parties if needed

        Return False if one of the messages is rejected.

        """

        if validated_data and 'recipients' in validated_data:  # action is "create"
            recipients = validated_data['recipients']
            new_messsage = DmMessage(subject=validated_data['subject'],
                                     body=validated_data['body'],
                                     sender=self.sender,
                                     moderation_status=STATUS_ACCEPTED)
        elif parent:  # action is "reply"
            if reply_all:
                recipients = validated_data['recipients']
            else:
                recipients = parent.sender
            quoted = parent.quote(*(format_subject, format_body))
            # print quoted, parent.subject
            sbjct = validated_data['subject'] if (validated_data and 'subject' in validated_data) else quoted['subject']
            # bdy = validated_data['body'] if (validated_data and 'body' in validated_data) else format_body(parent.sender, parent.body)
            new_messsage = DmMessage(subject=sbjct,
                                     body=validated_data['body'],
                                     sender=self.sender,
                                     moderation_status=STATUS_ACCEPTED)

        # print type(recipients), new_messsage.subject, new_messsage.body

        if parent and not parent.thread_id:  # at the very first reply, make it a conversation
            parent.thread = parent
            parent.save()
            # but delay the setting of parent.replied_at to the moderation step
        if parent:
            new_messsage.parent = parent
            new_messsage.thread_id = parent.thread_id

        initial_moderation = new_messsage.get_moderation()
        initial_dates = new_messsage.get_dates()
        initial_status = new_messsage.moderation_status
        if recipient:
            if isinstance(recipient, get_user_model()) and recipient in recipients:
                recipients.remove(recipient)
            recipients.insert(0, recipient)
        is_successful = True

        if isinstance(recipients, get_user_model()):  # change to list type
            recipients = [recipients]

        for r in recipients:
            usr_model = get_user_model()
            if isinstance(r, get_user_model()):
                new_messsage.recipient = r
            else:
                new_messsage.recipient = usr_model.objects.get(email=r)
            new_messsage.pk = None  # force_insert=True is not accessible from here
            new_messsage.auto_moderate(auto_moderators)
            new_messsage.clean_moderation(initial_status)
            new_messsage.clean_for_visitor()
            m = new_messsage.save()
            if new_messsage.is_rejected():
                is_successful = False
            new_messsage.update_parent(initial_status)
            # new_messsage.notify_users(initial_status, self.site)

            # some resets for next reuse
            if not isinstance(r, get_user_model()):
                new_messsage.email = ''
            new_messsage.set_moderation(*initial_moderation)
            new_messsage.set_dates(*initial_dates)
        return is_successful

    # commit_on_success() is deprecated in Django 1.6 and will be removed in Django 1.8
    create = transaction.atomic(create) if hasattr(transaction, 'atomic') else transaction.commit_on_success(create)

    class Meta:
        model = DmMessage
        fields = ('body', 'subject')


class WriteSerializer(BaseWriteSerializer):
    """The serializer for an authenticated user, to compose a message."""
    recipients = CommaSeparatedRecipientField(required=True)

    def __init__(self, *args, **kwargs):
        super(WriteSerializer, self).__init__(*args, **kwargs)

    class Meta(BaseWriteSerializer.Meta):
        fields = ('recipients', 'subject', 'body')


class AnonymousWriteSerializer(BaseWriteSerializer):
    """The serializer for an anonymous user, to compose a message."""
    # The 'max' customization should not be permitted here.
    # The features available to anonymous users should be kept to the strict minimum.

    can_overwrite_limits = False

    email = serializers.EmailField()
    recipients = CommaSeparatedRecipientField(max=2)  # one recipient is enough

    class Meta(BaseWriteSerializer.Meta):
        fields = ('email', 'recipients', 'subject', 'body')


# allow_copies = not getattr(settings, 'POSTMAN_DISALLOW_COPIES_ON_REPLY', False)
allow_copies = False
class WriteReplySerializer(BaseWriteSerializer):
    """The serializer for replying a message."""
    # if allow_copies:
    #     recipients = CommaSeparatedRecipientField(required=False)
    subject = serializers.CharField(required=False)

    def __init__(self, *args, **kwargs):
        self.parent = kwargs.pop('parent', None)
        self.recipient = self.parent.sender

        # set recipient
        if self.parent.sender:
            self.recipient = self.parent.sender
        elif self.parent.email:
            self.recipient = self.parent.email

        super(WriteReplySerializer, self).__init__(*args, **kwargs)

    class Meta(BaseWriteSerializer.Meta):
        fields = (['recipients'] if allow_copies else []) + ['subject', 'body']


class ForwardReplyAllSerializer(BaseWriteSerializer):
    recipients = CommaSeparatedRecipientField()  # one recipient is enough

    class Meta(BaseWriteSerializer.Meta):
        fields = ('recipients', 'subject', 'body')


class MessageDeleteSerializer(serializers.Serializer):
    """The serializer for delete undelete message(s)."""
    pks = serializers.IntegerField(required=False, allow_null=True)
    tpks = serializers.IntegerField(required=False, allow_null=True)

    def is_valid(self, **kwargs):
        super(MessageDeleteSerializer, self).is_valid(**kwargs)
        if not self.validated_data['pks'] and not self.validated_data['tpks']:
            raise serializers.ValidationError('Either field (pks/tpks) must be filled')
        return True
