from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def healthcheck(_request):
    return JsonResponse({'status': 'ok'})


urlpatterns = [
    path('healthz/', healthcheck),
    path('admin/', admin.site.urls),
    path('api/v1/', include('ledger.urls')),
]
