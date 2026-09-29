from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from azbankgateways.urls import az_bank_gateways_urls

urlpatterns = [
    path('admin/', admin.site.urls),
    path('admin-panel/', include('admin_panel.urls')),
    path('', include('home.urls')),
    path('middle-admin-panel/', include('middleAdmin_panel.urls')),
    path('payment/', include('payment_app.urls')),
    path('reports/', include('reports.urls')),
    path('notifications/', include('notifications.urls')),
    path('admin-payment/', include('admin_payment_app.urls')),
    path('user/', include('user_app.urls')),
    path('poll/', include('polls_app.urls')),
    path('ckeditor/', include('ckeditor_uploader.urls')),  # this is required
    path('select2/', include('django_select2.urls')),
    path('api/', include('mobileApp.urls')),
    # path('bankgateways/', az_bank_gateways_urls()),

]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
