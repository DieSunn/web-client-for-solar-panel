from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect
from django.contrib.auth.mixins import UserPassesTestMixin

def group_required(*group_names):
    """
    Декоратор, который проверяет, авторизован ли пользователь и принадлежит ли он хотя бы к одной из указанных групп.
    Если пользователь не авторизован, он будет перенаправлен на страницу входа.
    Если авторизован, но не принадлежит ни к одной из требуемых групп, он не сможет получить доступ.
    (По умолчанию user_passes_test перенаправляет на LOGIN_URL, если тест не пройден.)
    """
    def check_groups(user):
        # Проверяем, авторизован ли пользователь
        if user.is_authenticated:
            # Проверяем, является ли пользователь суперпользователем (у него полный доступ)
            if user.is_superuser:
                return True
            # Проверяем, принадлежит ли пользователь к одной из требуемых групп
            if user.groups.filter(name__in=group_names).exists():
                return True
        return False # Не авторизован или не принадлежит к нужной группе

    # user_passes_test перенаправляет на LOGIN_URL (из settings.py), если тест не пройден.
    # Вы можете явно указать login_url='/accounts/login/' или любой другой URL.
    return user_passes_test(check_groups, login_url='/accounts/login/')

# Конкретные декораторы для каждой роли
# Они обеспечивают иерархический доступ: Администратор имеет доступ ко всему,
# Оператор - к своим страницам + страницам Гостя, Гость - только к своим.
guest_access_required = group_required('Guest', 'Operator', 'Administrator')
operator_access_required = group_required('Operator', 'Administrator')
admin_access_required = group_required('Administrator')

def superuser_required():
    """
    Декоратор, который проверяет, является ли пользователь суперпользователем.
    Если пользователь не авторизован или не является суперпользователем,
    он будет перенаправлен на страницу входа.
    """
    def check_superuser(user):
        # Пользователь должен быть авторизован и быть суперпользователем
        return user.is_authenticated and user.is_superuser

    return user_passes_test(check_superuser, login_url='/accounts/login/')

superuser_access_required = superuser_required()