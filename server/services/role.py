"""角色库服务：模板 CRUD + 跨作品引用（副本）+ 用模板建角色。

模板字段集预置于 models/characters.DEFAULT_TEMPLATES；is_global 模板跨作品引用时创建副本，
副本改动不影响模板本身。
"""
from server.models import characters as cm
from server.services import character as char_svc


def list_templates():
    return cm.list_templates()


def create_template(name, category, fields, is_global=0):
    return cm.create_template(name, category, fields, is_global)


def get_template(tid):
    return cm.get_template(tid)


def instantiate(template_id, book_id, name):
    """用模板创建角色（副本）。"""
    return char_svc.instantiate_template(template_id, book_id, name)


def seed():
    cm.seed_templates()
