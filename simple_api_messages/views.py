# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from simple_api_messages import models
from django.shortcuts import render
import serializers

from django.contrib.auth.models import User, Group
from rest_framework import viewsets
from simple_api_messages.serializers import UserSerializer, GroupSerializer
from rest_framework import generics
from rest_framework.views import APIView as APIViewCore
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import detail_route, list_route
from rest_framework.permissions import DjangoObjectPermissions, IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.exceptions import ValidationError
from rest_framework.metadata import BaseMetadata
from rest_framework.decorators import api_view
from rest_framework.reverse import reverse
from rest_framework import exceptions, authentication
from postman.models import Message as DmMessage


class APIView(APIViewCore):
    pass

def get_recipient_email_from_id_list(recipients_ids=None):
    if not recipients_ids:
        return []

    # ids = [id for id in recipients_ids]
    recipients_email = []
    for id in recipients_ids:
        user = models.MyUser.objects.get(pk=id)
        recipients_email.append(user.email)
    return recipients_email

class UserViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    """
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = UserSerializer


class GroupViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows groups to be viewed or edited.
    """
    queryset = Group.objects.all()
    serializer_class = GroupSerializer


class BaseDmView(generics.GenericAPIView):
    """ Common code to manage the View.
        Dm = Direct Message (User-to-user private messaging)
    """

    # authentication_classes = (CsrfExemptSessionAuthentication, OAuth2Authentication, )
    permission_classes = (IsAuthenticated, )
    serializer_class = serializers.DmMessageSerializer
    # filter_backends = (filters.SearchFilter,)
    search_fields = ('subject', 'body')


class DmListView(BaseDmView):
    folder_name = 'inbox'

    def get_queryset(self, request):
        return getattr(DmMessage.objects, self.folder_name)(request.user)

    def get(self, request, *args, **kwargs):
        """
        Get list of Inbox Messages
        """
        return self.list(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset(request))

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class DmUnreadCountView(APIView):

    permission_classes = (IsAuthenticated,)

    def get(self, request, format=None):
        unread_count = DmMessage.objects.inbox_unread_count(request.user)
        return Response({'unread_count':unread_count}, status.HTTP_200_OK)


class DmSentView(DmListView):
    folder_name = 'sent'

    def get(self, request, *args, **kwargs):
        """
        Get list of Sent Messages
        """
        return self.list(request, *args, **kwargs)


class DmMarkArchive(BaseDmView):
    """
    view for mark message as archived.
    """

    field_bit = 'archived'
    field_value = True

    def get_queryset(self):
        return DmMessage.objects.all()

    def post(self, request, *args, **kwargs):
        return self.mark_archive(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        return self.mark_archive(request, *args, **kwargs)

    def mark_archive(self, request, *args, **kwargs):

        user = request.user
        instance = self.get_object()
        filter = Q(pk__in=[instance.pk]) | Q(thread__in=[instance.thread_id])

        recipient_rows = DmMessage.objects.as_recipient(user, filter).update(**{'recipient_{0}'.format(self.field_bit): self.field_value})
        sender_rows = DmMessage.objects.as_sender(user, filter).update(**{'sender_{0}'.format(self.field_bit): self.field_value})

        if not (recipient_rows or sender_rows):
            return Response({'detail':'Error Occured. Please Contact Administrator'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DmMarkRead(BaseDmView):
    """
    view for mark message as read.
    """

    def get_queryset(self):
        return DmMessage.objects.all()

    def post(self, request, *args, **kwargs):
        return self.mark_read(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        return self.mark_read(request, *args, **kwargs)

    def mark_read(self, request, *args, **kwargs):

        user = request.user
        instance = self.get_object()
        DmMessage.objects.set_read(user, Q(pk=instance.id))
        instance.refresh_from_db()
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DmArchivesView(DmListView):
    folder_name = 'archives'

    def get(self, request, *args, **kwargs):
        """
        Get list of Archived Messages
        """
        return self.list(request, *args, **kwargs)


class DmTrashView(DmListView):
    folder_name = 'trash'

    def get(self, request, *args, **kwargs):
        """
        Get list of Trash Messages
        """
        return self.list(request, *args, **kwargs)


class DmCreateMessageView(BaseDmView):
    """
    view for creating Message
    """

    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        """
        Create Message
        """
        # get user email from array of ids]
        try:

            user_id_list_serializer = serializers.UserIdListSerializer(data=request.data, context={'request': request})
            if not user_id_list_serializer.is_valid():
                return Response(user_id_list_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            recipients_email = get_recipient_email_from_id_list(user_id_list_serializer.data['recipients'])
        except Exception as e:
            logger.error( '%s (%s)' % (e.message, type(e)))
            return Response({e.message}, status=status.HTTP_400_BAD_REQUEST)

        # data = request.data
        extra_data = { 'sender' :self.request.user }
        request_params = {
            "subject": request.data['subject'],
            "body": request.data['body'],
            "recipients": ",".join(recipients_email),
        }
        # print 'kwargs', kwargs, 'request.data', request.data, request_params

        serializer = serializers.WriteSerializer(data=request_params, **extra_data)
        if serializer.is_valid():
            # print 'serializer.validated_data', serializer.validated_data
            result = serializer.create(serializer.validated_data)
            return Response(user_id_list_serializer.data, status.HTTP_201_CREATED)
        else:
            # print 'serializer.errors', serializer.errors
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DmThreadView(BaseDmView):
    """
    view for listing Messages in threaded/conversation format
    """
    permission_classes = (IsAuthenticated, )

    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        thread_id = kwargs.pop('thread_id', None)
        user = request.user
        try:
            thread_id = thread_id
            self.filter = Q(thread=thread_id)
            # self.msgs = DmMessage.objects.thread(user, self.filter)
            # if not self.msgs:
            #     raise ValidationError('Message thread not found.')
            # serializer = serializers.DmMessageSerializer(data=self.msgs, many=True)
            # DmMessage.objects.set_read(user, self.filter)

            queryset = DmMessage.objects.thread(user, self.filter)
            DmMessage.objects.set_read(user, self.filter)
        except Exception as e:
            return Response([e.message], 400)


        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)


class DmGetReplyDeleteView(BaseDmView):
    """
    view for retrieve, reply Message, delete message.
    """

    field_bit = 'deleted_at'
    field_value = None

    def get_queryset(self):
        return DmMessage.objects.all()

    def get(self, request, *args, **kwargs):
        """
        Get detail of Message
        """
        return self.retrieve(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        # queryset = self.filter_queryset(self.get_queryset())
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        return self.reply(request, *args, **kwargs)

    def reply(self, request, *args, **kwargs):
        """
        Reply Message
        """
        # data = request.data
        instance = self.get_object()
        try:
            extra_data = { 'sender' :self.request.user, 'parent':instance }
            # print 'pk', kwargs.pop('pk', None), 'extra_data', extra_data, 'request.data', request.data

            serializer = serializers.WriteReplySerializer(data=request.data, **extra_data)
            if serializer.is_valid():
                result = serializer.create(serializer.validated_data, **{'parent':instance })
                return Response(serializer.data, status.HTTP_201_CREATED)
            else:
                # print 'serializer.errors', serializer.errors
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            raise ValidationError([e.message])
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, *args, **kwargs):
        """
        view for deleting a message.
        """
        user = request.user
        instance = self.get_object()
        filter = Q(pk__in=[instance.pk]) | Q(thread__in=[instance.thread_id])
        # print 'user', user, 'filter', filter
        self.field_value = now()

        # set field_value=None to undelete message
        undelete = kwargs.pop('undelete', None)
        if undelete:
            self.field_value = None

        recipient_rows = DmMessage.objects.as_recipient(user, filter).update(**{'recipient_{0}'.format(self.field_bit): self.field_value})
        sender_rows = DmMessage.objects.as_sender(user, filter).update(**{'sender_{0}'.format(self.field_bit): self.field_value})

        # print recipient_rows, sender_rows

        if not (recipient_rows or sender_rows):
            return Response({'detail':'Error Occured. Please Contact Administrator'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_204_NO_CONTENT)


class DmForwardMessageView(BaseDmView):
    """
    Class for forwarding message.
    """

    def get_queryset(self):
        return DmMessage.objects.all()

    def post(self, request, *args, **kwargs):
        return self.forward(request, *args, **kwargs)

    def forward(self, request, *args, **kwargs):
        """
        Forward Message
        """

        instance = self.get_object()

        # get user email from array of ids]
        try:
            user_id_list_serializer = serializers.UserIdListSerializer(data=request.data, context={'request': request})
            if not user_id_list_serializer.is_valid():
                return Response(user_id_list_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            recipients_email = get_recipient_email_from_id_list(user_id_list_serializer.data['recipients'])

            extra_data = {'sender': self.request.user}
            request_params = {
                "subject": request.data['subject'],
                "body": request.data['body'],
                "recipients": ",".join(recipients_email),
            }

            # return Response(user_id_list_serializer.data, status.HTTP_200_OK)

            serializer = serializers.ForwardReplyAllSerializer(data=request_params, **extra_data)
            if serializer.is_valid():
                # print 'serializer.validated_data', serializer.validated_data
                result = serializer.create(serializer.validated_data)
                return Response(user_id_list_serializer.data, status.HTTP_201_CREATED)
            else:
                # print 'serializer.errors', serializer.errors
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            return Response(user_id_list_serializer.data, status.HTTP_200_OK)
        except Exception as e:
            logger.error( '%s (%s)' % (e.message, type(e)))
            raise ValidationError([e.message])
            # return Response({e.message}, status=status.HTTP_400_BAD_REQUEST)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DmReplyAllView(BaseDmView):

    def get_queryset(self):
        return DmMessage.objects.all()

    def post(self, request, *args, **kwargs):
        return self.reply_all(request, *args, **kwargs)

    def reply_all(self, request, *args, **kwargs):
        """
        Reply All Message
        """

        instance = self.get_object()

        # get user email from array of ids]
        try:
            user_id_list_serializer = serializers.UserIdListSerializer(data=request.data, context={'request': request})
            if not user_id_list_serializer.is_valid():
                return Response(user_id_list_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            recipients_email = get_recipient_email_from_id_list(user_id_list_serializer.data['recipients'])

            extra_data = {'sender': self.request.user}
            request_params = {
                "subject": request.data['subject'],
                "body": request.data['body'],
                "recipients": ",".join(recipients_email),
            }

            serializer = serializers.ForwardReplyAllSerializer(data=request_params, **extra_data)

            if serializer.is_valid():
                # print 'serializer.validated_data', serializer.validated_data
                result = serializer.create(serializer.validated_data, **{'parent':instance, 'reply_all':True })
                return Response(user_id_list_serializer.data, status.HTTP_201_CREATED)
            else:
                # print 'serializer.errors', serializer.errors
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            return Response(user_id_list_serializer.data, status.HTTP_200_OK)
        except Exception as e:
            logger.error( '%s (%s)' % (e.message, type(e)))
            raise ValidationError([e.message])
            # return Response({e.message}, status=status.HTTP_400_BAD_REQUEST)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

