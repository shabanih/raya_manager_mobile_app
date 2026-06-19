from django.urls import path
from home import views
from home.views import house_login

urlpatterns = [
    path('', views.index, name='home'),
    path('home-login/', views.house_login, name='house_login_subdomain'),
    path('middle/login/', views.middle_login, name='login_middle'),
    path('test/', views.test_subdomain, name='test_subdomain'),
    path('about-us/', views.about_us_view, name='about_us'),
    path('contact-us/', views.contact_us_view, name='contact_us'),
    path('articles/', views.articles_view, name='articles'),
    path('article/details/<int:article_id>/', views.article_details_view, name='article_details'),
    path('introduction/', views.introduction_view, name='introduction'),
    path('add-comment/', views.add_comment, name='add_comment'),
    path('user-charge-select/', views.charge_select, name='charge_select'),
    path('register-house-by-user/', views.register_house_by_user, name='register_house_by_user'),
    path(
        'buy-subscription-by-user/<int:user_id>/',
        views.buy_subscription_by_user,
        name='buy_subscription_by_user'
    )
]
