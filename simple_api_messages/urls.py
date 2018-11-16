"""api_message_django URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf.urls import url, include
from django.contrib.auth.models import User
from rest_framework import routers
from simple_api_messages import views


router = routers.DefaultRouter()
router.register(r'users', views.UserViewSet)
router.register(r'groups', views.GroupViewSet)

urlpatterns = [
    # url(r'^admin/', admin.site.urls),
    url(r'^', include(router.urls)),
    url(r'^api-auth/', include('rest_framework.urls')),
    url(r'^inbox/$', views.DmListView.as_view(), name='inbox'),
    url(r'^unread_count/$', views.DmUnreadCountView.as_view(), name='unread_count'),
    url(r'^sent/$', views.DmSentView.as_view(), name='sent'),
    # url(r'^draft/$', views.DmDraft.as_view(), name='draft'),
    url(r'^archive/(?P<pk>[0-9a-zA-Z]+)/$', views.DmMarkArchive.as_view(), name='mark_archive'),
    url(r'^mark_read/(?P<pk>[0-9a-zA-Z]+)/$', views.DmMarkRead.as_view(), name='mark_read'),
    url(r'^archives/$', views.DmArchivesView.as_view(), name='archives'),
    url(r'^trash/$', views.DmTrashView.as_view(), name='trash'),
    url(r'^msg/$', views.DmCreateMessageView.as_view(), name='create'),
    url(r'^msg/(?P<pk>[0-9a-zA-Z]+)/$', views.DmGetReplyDeleteView.as_view(), name='get_reply_delete'),
    url(r'^thread/(?P<thread_id>[0-9a-zA-Z]+)/$', views.DmThreadView.as_view(), name='thread_view'),
    url(r'^msg/forward_message/(?P<pk>[0-9a-zA-Z]+)/$', views.DmForwardMessageView.as_view(), name='forward_message'),
    url(r'^msg/reply_all/(?P<pk>[0-9a-zA-Z]+)/$', views.DmReplyAllView.as_view(), name='reply_all'),
]
