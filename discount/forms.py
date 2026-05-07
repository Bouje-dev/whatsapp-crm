# forms.py
from django import forms 
from .models import CustomUser
from django.contrib.auth.forms import UserCreationForm



class ExternalTokenForm(forms.Form):
    platform = forms.ChoiceField(label='Platform' , choices=[
        ('COD network', 'Cod network'),
    ])
    access_token = forms.CharField(widget=forms.PasswordInput)
    tokenname = forms.CharField(label='Token Name', max_length=100, required=False, help_text='Optional: Name for the token')


class LoginForm(forms.Form):
        username = forms.CharField(label='Username', max_length=150)
        password = forms.CharField(widget=forms.PasswordInput, label='Password')



class CustomUserCreationForm(UserCreationForm):
    password2 = None  # إزالة حقل تأكيد كلمة السر

    class Meta:
        model = CustomUser
        fields = ('user_name', 'email', 'password1')


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'password2' in self.fields:
            del self.fields['password2']




class PasswordChangeForm(forms.Form):
    old_password = forms.CharField(widget=forms.PasswordInput, label='Old Password')
    new_password = forms.CharField(widget=forms.PasswordInput, label='New Password')
    confirm_password = forms.CharField(widget=forms.PasswordInput, label='Confirm New Password')

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        confirm_password = cleaned_data.get("confirm_password")

        if new_password and confirm_password and new_password != confirm_password:
            raise forms.ValidationError("New password and confirmation do not match.")
        
        return cleaned_data
    



class LoginForm(forms.Form):
    email = forms.EmailField(label="البريد الإلكتروني")
    password = forms.CharField(widget=forms.PasswordInput, label="كلمة المرور")
