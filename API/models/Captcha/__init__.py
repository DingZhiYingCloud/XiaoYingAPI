# 自研图形验证码业务域
from API.models.Captcha.behavior import BehaviorSample
from API.models.Captcha.captcha import CaptchaChallenge
from API.models.Captcha.click_word import ClickWordChallenge
from API.models.Captcha.slider import SliderChallenge
from API.models.Captcha.stat import CaptchaStat

__all__ = ['BehaviorSample', 'CaptchaChallenge', 'ClickWordChallenge', 'SliderChallenge', 'CaptchaStat']
