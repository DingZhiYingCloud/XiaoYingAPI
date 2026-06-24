import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-fallback-key-change-in-production')

DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '*').split(',')

# 跨域设置
SECURE_CROSS_ORIGIN_OPENER_POLICY = "None"
# 跨域请求配置，允许所有源的跨域请求
CORS_ORIGIN_ALLOW_ALL = True


# 应用定义配置
# https://docs.djangoproject.com/en/5.2/ref/settings/#installed-apps

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders', # 跨域请求中间件
    'API.apps.ApiConfig', # 自定义API应用配置,用来处理API服务相关的请求和响应
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware', # 全站批量设置安全相关 HTTP 响应头，防御多种浏览器层面攻击，是全站安全第一道防线
    'django.contrib.sessions.middleware.SessionMiddleware', # 实现 Django 会话（Session）机制，维护用户服务端状态。
    'corsheaders.middleware.CorsMiddleware', # 跨域请求中间件
    'django.middleware.common.CommonMiddleware', # 用来处理如日志记录、请求计数等通用任务的中间件
    # 'django.middleware.csrf.CsrfViewMiddleware', # 用来处理CSRF攻击的中间件
    'django.contrib.auth.middleware.AuthenticationMiddleware', # 认证中间件,用来处理用户认证相关的请求和响应
    'django.contrib.messages.middleware.MessageMiddleware', # 消息中间件,用来处理消息相关的请求和响应
    'django.middleware.clickjacking.XFrameOptionsMiddleware', # 用来处理点击劫持攻击的中间件
]

ROOT_URLCONF = 'XiaoYingAPI.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # 全局模板目录:用于覆盖 Django 内置模板(如 admin/base_site.html 自定义 favicon)
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'XiaoYingAPI.wsgi.application'


# 数据库配置
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# 密码验证配置
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# 国际化配置
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'zh-hans' # 中文简体

TIME_ZONE = 'Asia/Shanghai' # 上海时间

USE_I18N = True # 开启国际化

USE_TZ = True # 开启时区支持


# 静态文件配置,比如CSS,JavaScript,Images等
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')


# 默认主键字段类型配置
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 媒体文件配置
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


# ==================== 邮箱 SMTP 配置 ====================
# 使用 QQ 邮箱作为默认发件邮箱
# 凭据从项目根目录的 .env 文件读取:
#   QQ邮箱账号     - QQ邮箱地址(发件人)
#   QQ邮箱授权码   - QQ邮箱SMTP授权码(非登录密码,需在QQ邮箱设置中开启SMTP服务后获取)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'  # 使用SMTP后端发送真实邮件
EMAIL_HOST = 'smtp.qq.com'          # QQ邮箱SMTP服务器地址
EMAIL_PORT = 465                    # QQ邮箱SMTP SSL端口
EMAIL_USE_SSL = True                # 启用SSL加密传输
EMAIL_HOST_USER = os.getenv('QQ邮箱账号', '')        # 发件邮箱账号
EMAIL_HOST_PASSWORD = os.getenv('QQ邮箱授权码', '')  # 发件邮箱授权码
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER  # 默认发件人地址(与发件账号一致)
