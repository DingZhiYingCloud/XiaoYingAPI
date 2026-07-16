"""
sqlite_orm - 可移植、简洁、高性能的 SQLite3 ORM 模块

====================================================================
设计理念
====================================================================
- 可移植：仅依赖 Python 标准库 sqlite3，一个 .py 文件随处可用
- 简洁性：参考 Django ORM 的 Model/QuerySet API，上手即用
- 性能：WAL 模式、参数化查询、批量操作、延迟求值、缓存编译的 SQL
- 稳定性：完整的异常体系、类型转换、空安全、事务管理

====================================================================
快速开始
====================================================================

    from API.common.sqlite_orm import Database, Model, fields

    # 1. 定义模型
    class User(Model):
        name = fields.CharField(max_length=100, index=True)
        age = fields.IntegerField(default=0)
        email = fields.CharField(max_length=200, null=True)

        class Meta:
            table_name = 'users'
            ordering = '-id'

    # 2. 连接数据库
    db = Database('path/to/data.db')
    db.register(User)
    db.create_tables()      # 自动建表

    # 3. 增
    user = User(name='Alice', age=25, email='alice@example.com')
    user.save()

    # 批量增
    User.objects.bulk_create([
        User(name='Bob', age=30),
        User(name='Charlie', age=35),
    ])

    # 4. 查
    user = User.objects.get(id=1)
    users = User.objects.filter(age__gte=18).order_by('-age').limit(10).all()
    count = User.objects.filter(age__gt=20).count()
    exists = User.objects.filter(email=None).exists()

    # 5. 改
    user.age = 26
    user.save()
    User.objects.filter(age__lt=18).update(age=18)

    # 6. 删
    user.delete()
    User.objects.filter(age__gt=60).delete()

    # 7. 事务
    with db.transaction():
        user.save()
        another.save()

    # 8. 迁移到其他项目：复制 sqlite_orm.py 即可
"""

import sqlite3
import threading
from datetime import datetime
from typing import (
    Any,
    Dict,
    Generic,
    Generator,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
)

# ──────────────────────────────────────────────
# 异常体系
# ──────────────────────────────────────────────


class ORMError(Exception):
    """ORM 基类异常"""


class ConnectionError(ORMError):
    """数据库连接相关错误"""


class IntegrityError(ORMError):
    """数据完整性违反错误（主键、唯一约束等）"""


class NotFoundError(ORMError):
    """查询结果不存在"""


class FieldError(ORMError):
    """字段定义或使用错误"""


# ──────────────────────────────────────────────
# 类型别名 & 工具常量
# ──────────────────────────────────────────────

_T = TypeVar("_T", bound="Model")
_SQL_LOOKUP_CACHE: Dict[str, str] = {}

# 字段类型 -> SQLite 类型映射
FIELD_TYPE_MAP: Dict[type, str] = {
    int: "INTEGER",
    float: "REAL",
    str: "TEXT",
    bytes: "BLOB",
    bool: "SMALLINT",
    datetime: "TIMESTAMP",
    type(None): "NULL",
}

# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────


def _to_sql_value(value: Any) -> Any:
    """将 Python 值转换为 SQLite 可存储的值。

    性能提示：提前转换避免 sqlite3 运行时的类型推断开销。
    """
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, bool):
        return 1 if value else 0
    return value


def _from_sql_value(value: Any, py_type: type) -> Any:
    """将 SQLite 返回值转换回 Python 类型。"""
    if value is None:
        return None
    if py_type is datetime and isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    if py_type is bool:
        return bool(value)
    return value


def _parse_lookup(key: str) -> Tuple[str, str]:
    """解析 Django 风格的字段查找表达式。

    例如 'age__gte' -> ('age', 'gte'), 'name' -> ('name', 'exact')
    """
    parts = key.rsplit("__", 1)
    if len(parts) == 2 and parts[1] in LOOKUP_MAP:
        return parts[0], parts[1]
    return parts[0], "exact"


# ──────────────────────────────────────────────
# 查找操作映射（性能：编译为模块级常量）
# ──────────────────────────────────────────────

LOOKUP_MAP = {
    "exact": "= ?",
    "iexact": "LIKE ?",
    "ne": "!= ?",
    "gt": "> ?",
    "gte": ">= ?",
    "lt": "< ?",
    "lte": "<= ?",
    "contains": "LIKE ?",
    "icontains": "LIKE ?",
    "startswith": "LIKE ?",
    "istartswith": "LIKE ?",
    "endswith": "LIKE ?",
    "iendswith": "LIKE ?",
    "in": "IN ({})",
    "not_in": "NOT IN ({})",
    "isnull": "IS NULL",
}

# 大小写不敏感的查找（与 LIKE 同义，因为 SQLite LIKE 默认不区分大小写）
_CI_LOOKUPS = frozenset(
    {"iexact", "icontains", "istartswith", "iendswith"}
)

# 需要值转换的查找
_VALUE_TRANSFORM_MAP = {
    "contains": lambda v: f"%{v}%",
    "icontains": lambda v: f"%{v}%",
    "startswith": lambda v: f"{v}%",
    "istartswith": lambda v: f"{v}%",
    "endswith": lambda v: f"%{v}",
    "iendswith": lambda v: f"%{v}",
    "isnull": lambda v: None,  # 值不会被使用
}


def _transform_lookup_value(lookup: str, value: Any) -> Any:
    """根据查找类型转换值。"""
    transformer = _VALUE_TRANSFORM_MAP.get(lookup)
    return transformer(value) if transformer else value


# ──────────────────────────────────────────────
# Fields - 字段定义
# ──────────────────────────────────────────────


class Field:
    """字段基类，用于定义模型列的元信息。"""

    _counter = 0  # 类级别计数器，用于保持字段定义顺序

    __slots__ = (
        "_name",
        "_order",
        "default",
        "null",
        "unique",
        "index",
        "primary_key",
        "max_length",
        "py_type",
        "sql_type",
        "description",
    )

    def __init__(
        self,
        py_type: type,
        sql_type: str = "TEXT",
        default: Any = None,
        null: bool = False,
        unique: bool = False,
        index: bool = False,
        primary_key: bool = False,
        max_length: Optional[int] = None,
        description: str = "",
    ):
        Field._counter += 1
        self._order = Field._counter
        self._name = ""  # 由 ModelMeta 在类创建时设置
        self.default = default
        self.null = null
        self.unique = unique
        self.index = index
        self.primary_key = primary_key
        self.max_length = max_length
        self.py_type = py_type
        self.sql_type = sql_type
        self.description = description

    def to_ddl(self) -> str:
        """生成列定义的 DDL 语句片段。"""
        parts = [f'"{self._name}"', self.sql_type]
        if self.primary_key:
            parts.append("PRIMARY KEY")
        if not self.null and not self.primary_key:
            parts.append("NOT NULL")
        if self.unique:
            parts.append("UNIQUE")
        if self.default is not None:
            default_val = _to_sql_value(self.default)
            if isinstance(default_val, str):
                parts.append(f"DEFAULT '{default_val}'")
            else:
                parts.append(f"DEFAULT {default_val}")
        return " ".join(parts)

    def to_index_ddl(self, table_name: str) -> Optional[str]:
        """生成索引 DDL；索引字段才返回。"""
        if self.index and not self.primary_key and not self.unique:
            return (
                f'CREATE INDEX IF NOT EXISTS idx_{table_name}_{self._name} '
                f'ON "{table_name}" ("{self._name}")'
            )
        return None


class IntegerField(Field):
    """整数字段 -> INTEGER"""

    def __init__(self, **kwargs):
        super().__init__(py_type=int, sql_type="INTEGER", **kwargs)


class FloatField(Field):
    """浮点数字段 -> REAL"""

    def __init__(self, **kwargs):
        super().__init__(py_type=float, sql_type="REAL", **kwargs)


class CharField(Field):
    """字符串字段 -> VARCHAR(n) 或 TEXT"""

    def __init__(self, max_length: Optional[int] = None, **kwargs):
        sql_type = f"VARCHAR({max_length})" if max_length else "TEXT"
        super().__init__(py_type=str, sql_type=sql_type, max_length=max_length, **kwargs)


class TextField(Field):
    """文本字段 -> TEXT"""

    def __init__(self, **kwargs):
        super().__init__(py_type=str, sql_type="TEXT", **kwargs)


class BooleanField(Field):
    """布尔字段 -> SMALLINT（存 0/1）"""

    def __init__(self, **kwargs):
        super().__init__(py_type=bool, sql_type="SMALLINT", **kwargs)


class DateTimeField(Field):
    """日期时间字段 -> TIMESTAMP"""

    def __init__(self, auto_now: bool = False, auto_now_add: bool = False, **kwargs):
        super().__init__(py_type=datetime, sql_type="TIMESTAMP", **kwargs)
        self.auto_now = auto_now
        self.auto_now_add = auto_now_add


class BlobField(Field):
    """二进制字段 -> BLOB"""

    def __init__(self, **kwargs):
        super().__init__(py_type=bytes, sql_type="BLOB", **kwargs)


# ──────────────────────────────────────────────
# ModelMeta - 元类，自动收集字段信息
# ──────────────────────────────────────────────


class ModelMeta(type):
    """元类：自动收集 Model 子类的 Field 定义，构建列元信息。"""

    def __new__(mcs, name: str, bases: Tuple[type, ...], namespace: Dict[str, Any]):
        if name == "Model":
            return super().__new__(mcs, name, bases, namespace)

        # 收集当前类定义的字段（按注册顺序排序）
        fields: Dict[str, Field] = {}
        for attr_name, attr_value in namespace.items():
            if isinstance(attr_value, Field):
                attr_value._name = attr_name
                fields[attr_name] = attr_value

        # 从父类继承字段
        for base in bases:
            if hasattr(base, "_meta") and base._meta:
                for fname, fobj in base._meta.fields.items():
                    if fname not in fields:
                        fields[fname] = fobj

        # 确保有主键，如果没有定义则自动添加 id
        has_pk = any(f.primary_key for f in fields.values())
        pk_name: str = ""
        if not has_pk:
            pk_field = IntegerField(primary_key=True, description="自增主键")
            pk_field._name = "id"
            pk_field._order = -1  # 确保排在最前面
            fields = {"id": pk_field, **fields}
            pk_name = "id"
        else:
            for fn, fv in fields.items():
                if fv.primary_key:
                    pk_name = fn
                    break

        # 按注册顺序排序字段
        sorted_fields = dict(sorted(fields.items(), key=lambda x: x[1]._order))

        # 收集 Meta 配置
        meta = namespace.get("Meta")
        table_name = getattr(meta, "table_name", name.lower())
        ordering = getattr(meta, "ordering", "")

        # 构建 _meta，注入 namespace，使 Model 子类可直接访问
        meta_info = _ModelMetaInfo(
            table_name=table_name,
            fields=sorted_fields,
            field_names=list(sorted_fields.keys()),
            pk_name=pk_name,
            ordering=ordering,
            db=None,
        )
        namespace["_meta"] = meta_info

        cls = super().__new__(mcs, name, bases, namespace)
        return cls


class _ModelMetaInfo:
    """存放模型元信息的轻量对象。使用 __slots__ 减少内存占用。"""

    __slots__ = (
        "table_name",
        "fields",
        "field_names",
        "pk_name",
        "ordering",
        "db",
    )

    def __init__(
        self,
        table_name: str,
        fields: Dict[str, Field],
        field_names: List[str],
        pk_name: str,
        ordering: str,
        db: Optional["Database"],
    ):
        self.table_name = table_name
        self.fields = fields
        self.field_names = field_names
        self.pk_name = pk_name
        self.ordering = ordering
        self.db = db


# ──────────────────────────────────────────────
# Model - 模型基类
# ──────────────────────────────────────────────


class Model(metaclass=ModelMeta):
    """所有业务模型的基类。提供 save()、delete() 等 CRUD 操作。

    继承此类，定义 Field 属性作为列，通过 objects 管理器执行查询。
    """

    objects: "Manager"  # 由 Manager.__set_name__ 设置

    def __init__(self, **kwargs):
        """初始化模型实例，设置字段默认值并接受关键字参数。"""
        for fname, field in self._meta.fields.items():
            if fname in kwargs:
                value = kwargs.pop(fname)
                setattr(self, fname, value)
            elif field.default is not None:
                setattr(self, fname, field.default)
            elif field.null:
                setattr(self, fname, None)
            elif field.primary_key:
                # 自增主键初始为 None，由数据库生成
                setattr(self, fname, None)
            else:
                pass

        if kwargs:
            raise FieldError(
                f"'{type(self).__name__}' 收到了未知参数: {list(kwargs.keys())}"
            )

        self._exists = False  # 标记是否已持久化

    def __setattr__(self, name: str, value: Any):
        """设置属性时进行类型转换（确保写入数据库的类型正确）。"""
        if name in self._meta.fields:
            field = self._meta.fields[name]
            if value is not None and field.py_type is not type(None):
                if field.py_type is bool:
                    value = bool(value)
                elif field.py_type is int:
                    value = int(value) if not isinstance(value, bool) else int(value)
                elif field.py_type is float:
                    value = float(value)
                elif field.py_type is str:
                    value = str(value)
        super().__setattr__(name, value)

    def __repr__(self) -> str:
        pk_val = getattr(self, self._meta.pk_name, None)
        return f"<{type(self).__name__}({self._meta.pk_name}={pk_val})>"

    # ───────── CRUD ─────────

    def save(self) -> "Model":
        """保存模型实例。

        新实例执行 INSERT，已有实例执行 UPDATE。
        使用 INSERT OR REPLACE 确保原子性。
        """
        self._before_save()
        data = {}
        for fname in self._meta.field_names:
            val = getattr(self, fname, None)
            # 处理 auto_now / auto_now_add
            field = self._meta.fields[fname]
            now = datetime.now()
            if isinstance(field, DateTimeField):
                if field.auto_now:
                    val = now
                    setattr(self, fname, now)
                elif field.auto_now_add and not self._exists:
                    val = now
                    setattr(self, fname, now)
            data[fname] = _to_sql_value(val)

        db = self._get_db()
        pk_name = self._meta.pk_name
        table = self._meta.table_name

        if self._exists:
            # UPDATE
            set_fields = [f for f in self._meta.field_names if f != pk_name]
            sql = (
                f'UPDATE "{table}" SET '
                f'{", ".join(f'"{f}"=?' for f in set_fields)} '
                f'WHERE "{pk_name}"=?'
            )
            params = [data[f] for f in set_fields] + [data[pk_name]]
            db._execute(sql, params)
        else:
            # INSERT
            cols = [f for f in self._meta.field_names]
            placeholders = ", ".join("?" for _ in cols)
            sql = f'INSERT INTO "{table}" ({", ".join(f'"{c}"' for c in cols)}) VALUES ({placeholders})'
            params = [data[f] for f in cols]
            cursor = db._execute(sql, params)
            # 如果没有显式设置主键，自动填充自增 ID
            if data.get(pk_name) is None:
                setattr(self, pk_name, cursor.lastrowid)
            self._exists = True

        self._after_save()
        return self

    def delete(self) -> int:
        """删除当前模型实例对应的数据库行。返回受影响行数。"""
        if not self._exists:
            return 0
        db = self._get_db()
        pk_name = self._meta.pk_name
        pk_val = getattr(self, pk_name, None)
        if pk_val is None:
            return 0
        sql = f'DELETE FROM "{self._meta.table_name}" WHERE "{pk_name}"=?'
        cursor = db._execute(sql, [pk_val])
        self._exists = False
        return cursor.rowcount

    def _before_save(self):
        """保存前的钩子，子类可重写。"""

    def _after_save(self):
        """保存后的钩子，子类可重写。"""

    def _get_db(self) -> "Database":
        """获取当前模型关联的数据库实例。"""
        db = self._meta.db
        if db is None:
            raise ConnectionError(
                f"模型 {type(self).__name__} 尚未关联数据库，"
                f"请先调用 Database.register({type(self).__name__})"
            )
        return db

    # ─── 类方法 ───

    @classmethod
    def _table_exists(cls, db: "Database") -> bool:
        """检查数据库中是否已存在当前模型的表。"""
        cursor = db._execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            [cls._meta.table_name],
        )
        return cursor.fetchone() is not None


# ──────────────────────────────────────────────
# QuerySet - 延迟求值的查询集
# ──────────────────────────────────────────────


class QuerySet(Generic[_T]):
    """延迟求值的 SQL 查询构建器，支持链式调用。

    QuerySet 的设计核心：
    - 所有修改操作都返回新的 QuerySet 实例（不可变风格）
    - 只在迭代或调用 .all()/.first()/.count() 等终端方法时才执行 SQL
    - 缓存编译的 SQL 模板避免重复解析
    """

    def __init__(self, model_cls: Type[_T], db: "Database"):
        self._model_cls = model_cls
        self._db = db
        self._meta = model_cls._meta

        # 查询构建状态
        self._where_clauses: List[str] = []
        self._params: List[Any] = []
        self._order_by_clauses: List[str] = []
        self._limit_val: Optional[int] = None
        self._offset_val: Optional[int] = None
        self._select_fields: Optional[List[str]] = None
        self._values_mode: Optional[str] = None  # None=model, 'dict', 'tuple', 'flat'

        # SQL 缓存（避免重复编译）
        self._cached_sql: Optional[str] = None
        self._cached_count_sql: Optional[str] = None

    def _clone(self) -> "QuerySet[_T]":
        """创建一个状态相同的新 QuerySet（深拷贝状态）。"""
        qs = QuerySet(self._model_cls, self._db)
        qs._where_clauses = list(self._where_clauses)
        qs._params = list(self._params)
        qs._order_by_clauses = list(self._order_by_clauses)
        qs._limit_val = self._limit_val
        qs._offset_val = self._offset_val
        qs._select_fields = list(self._select_fields) if self._select_fields else None
        qs._values_mode = self._values_mode
        return qs

    def _invalidate_cache(self):
        """使 SQL 缓存失效。"""
        self._cached_sql = None
        self._cached_count_sql = None

    def _make_param(self, value: Any) -> Any:
        """将 Python 值转为 SQL 参数。"""
        return _to_sql_value(value)

    # ─── 查询构建 API ───

    def filter(self, _query: Optional[str] = None, **kwargs) -> "QuerySet[_T]":
        """添加过滤条件（AND 关系）。

        支持 Django 风格的查找表达式：
            filter(age__gte=18, name__contains='Ali')
        也支持原始 SQL 片段：
            filter("age > 18")
        """
        qs = self._clone()
        if _query is not None:
            if kwargs:
                raise FieldError("同时使用原始 SQL 和关键字参数是不允许的")
            qs._where_clauses.append(f"({_query})")
            qs._invalidate_cache()
            return qs
        if not kwargs:
            return qs

        clauses, params = qs._resolve_lookups(kwargs)
        if clauses:
            qs._where_clauses.append(f"({' AND '.join(clauses)})")
            qs._params.extend(params)
            qs._invalidate_cache()
        return qs

    def exclude(self, **kwargs) -> "QuerySet[_T]":
        """排除匹配条件的数据（NOT）。"""
        if not kwargs:
            return self._clone()
        qs = self._clone()
        clauses, params = qs._resolve_lookups(kwargs)
        if clauses:
            qs._where_clauses.append(f"(NOT ({' OR '.join(clauses)}))")
            qs._params.extend(params)
            qs._invalidate_cache()
        return qs

    def order_by(self, *fields: str) -> "QuerySet[_T]":
        """排序。

        用法：
            .order_by('name')       # ASC
            .order_by('-age')       # DESC
            .order_by('name', '-age')
        """
        qs = self._clone()
        qs._order_by_clauses = []
        for f in fields:
            if f.startswith("-"):
                qs._order_by_clauses.append(f'"{f[1:]}" DESC')
            else:
                qs._order_by_clauses.append(f'"{f}"')
        qs._invalidate_cache()
        return qs

    def limit(self, n: int) -> "QuerySet[_T]":
        """限制返回记录数。"""
        qs = self._clone()
        qs._limit_val = n
        qs._invalidate_cache()
        return qs

    def offset(self, n: int) -> "QuerySet[_T]":
        """设置偏移量（常与 limit 配合实现分页）。"""
        qs = self._clone()
        qs._offset_val = n
        qs._invalidate_cache()
        return qs

    def values(self, *fields: str) -> "QuerySet[_T]":
        """仅查询指定字段，返回字典列表（而非模型实例）。

        用法:
            User.objects.values('name', 'age').all()
            # -> [{'name': 'Alice', 'age': 25}, ...]
        """
        if not fields:
            return self._clone()
        qs = self._clone()
        for f in fields:
            if f not in self._meta.fields:
                raise FieldError(
                    f"模型 {self._model_cls.__name__} 没有字段 '{f}'"
                )
        qs._select_fields = list(fields)
        qs._values_mode = 'dict'
        qs._invalidate_cache()
        return qs

    def values_list(self, *fields: str, flat: bool = False) -> "QuerySet[_T]":
        """仅查询指定字段，返回元组列表。

        用法:
            User.objects.values_list('name', 'age').all()
            # -> [('Alice', 25), ...]

            User.objects.values_list('name', flat=True).all()
            # -> ['Alice', 'Bob', ...]
        """
        if not fields:
            return self._clone()
        qs = self._clone()
        for f in fields:
            if f not in self._meta.fields:
                raise FieldError(
                    f"模型 {self._model_cls.__name__} 没有字段 '{f}'"
                )
        qs._select_fields = list(fields)
        qs._values_mode = 'flat' if flat else 'tuple'
        qs._invalidate_cache()
        return qs

    # ─── 终端操作（触发 SQL 执行）───

    def all(self) -> List[_T]:
        """执行查询，返回所有匹配的模型实例列表。"""
        return list(self._execute())

    def first(self) -> Optional[_T]:
        """返回第一条匹配的记录，或 None。"""
        return self.limit(1)._execute_first()

    def get(self, **kwargs) -> _T:
        """返回唯一一条匹配的记录，不存在或存在多条时抛异常。"""
        if kwargs:
            return self.filter(**kwargs)._get_one()
        return self._get_one()

    def count(self) -> int:
        """返回匹配记录数（使用 COUNT(*) 优化）。"""
        sql = self._build_count_sql()
        cursor = self._db._execute(sql, self._params)
        row = cursor.fetchone()
        return row[0] if row else 0

    def exists(self) -> bool:
        """判断是否存在匹配记录（使用 EXISTS 优化）。"""
        sql = self._build_exists_sql()
        cursor = self._db._execute(sql, self._params)
        row = cursor.fetchone()
        return bool(row[0]) if row else False

    def iterator(self, batch_size: int = 1000) -> Generator[_T, None, None]:
        """分批迭代查询结果，适合处理大量数据时节省内存。"""
        cursor = self._db._execute(self._build_sql(), self._build_params())
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                yield self._row_to_model(row)

    def update(self, **kwargs) -> int:
        """批量更新匹配的记录，返回受影响行数。"""
        if not kwargs:
            return 0
        set_clauses = []
        params = []
        for key, value in kwargs.items():
            if key not in self._meta.fields:
                raise FieldError(
                    f"模型 {self._model_cls.__name__} 没有字段 '{key}'"
                )
            set_clauses.append(f'"{key}"=?')
            params.append(_to_sql_value(value))

        sql = (
            f'UPDATE "{self._meta.table_name}" '
            f"SET {', '.join(set_clauses)}"
        )
        if self._where_clauses:
            sql += " WHERE " + " AND ".join(self._where_clauses)
        params.extend(self._params)

        cursor = self._db._execute(sql, params)
        return cursor.rowcount

    def delete(self) -> int:
        """批量删除匹配的记录，返回受影响行数。"""
        sql = f'DELETE FROM "{self._meta.table_name}"'
        if self._where_clauses:
            sql += " WHERE " + " AND ".join(self._where_clauses)
        cursor = self._db._execute(sql, self._params)
        return cursor.rowcount

    def paginate(self, page: int, page_size: int = 20) -> "Page[_T]":
        """分页查询，返回 Page 对象。

        Args:
            page: 页码，从 1 开始
            page_size: 每页数量

        Returns:
            Page 对象，包含 .items、.total、.page、.page_size、.pages
        """
        total = self.count()
        pages = max(1, (total + page_size - 1) // page_size)
        items = (
            self.limit(page_size).offset((page - 1) * page_size).all()
            if total > 0
            else []
        )
        return Page(items=items, total=total, page=page, page_size=page_size, pages=pages)

    def in_bulk(self, id_list: List[Any], field_name: Optional[str] = None) -> Dict[Any, _T]:
        """根据主键列表批量查询，返回 {pk: model} 字典。

        Args:
            id_list: 主键值列表
            field_name: 查询字段，默认使用主键
        """
        if not id_list:
            return {}
        fname = field_name or self._meta.pk_name
        return {
            getattr(obj, fname): obj
            for obj in self.filter(**{f"{fname}__in": id_list}).all()
        }

    # ─── 内部方法 ───

    def _resolve_lookups(
        self, kwargs: Dict[str, Any]
    ) -> Tuple[List[str], List[Any]]:
        """将字段查找表达式解析为 SQL 子句和参数列表。"""
        clauses: List[str] = []
        params: List[Any] = []

        for key, value in kwargs.items():
            field_name, lookup = _parse_lookup(key)
            if field_name not in self._meta.fields:
                raise FieldError(
                    f"模型 {self._model_cls.__name__} 没有字段 '{field_name}'"
                )

            sql_op = LOOKUP_MAP[lookup]

            if lookup == "isnull":
                if value:
                    clauses.append(f'"{field_name}" IS NULL')
                else:
                    clauses.append(f'"{field_name}" IS NOT NULL')
                continue

            if lookup in ("in", "not_in"):
                if not isinstance(value, (list, tuple, set)):
                    value = [value]
                placeholders = ", ".join("?" for _ in value)
                sql_op = sql_op.format(placeholders)
                params.extend(_to_sql_value(v) for v in value)
                clauses.append(f'"{field_name}" {sql_op}')
                continue

            val = _transform_lookup_value(lookup, value)
            # 如果值为 None，用 IS NULL 代替
            if val is None and lookup in ("exact",):
                clauses.append(f'"{field_name}" IS NULL')
            else:
                params.append(_to_sql_value(val))
                clauses.append(f'"{field_name}" {sql_op}')

        return clauses, params

    def _build_sql(self) -> str:
        """构建完整的 SELECT SQL（带缓存）。"""
        if self._cached_sql:
            return self._cached_sql

        if self._select_fields:
            select_expr = ", ".join(f'"{f}"' for f in self._select_fields)
        else:
            select_expr = "*"

        sql = f"SELECT {select_expr} FROM \"{self._meta.table_name}\""

        if self._where_clauses:
            sql += " WHERE " + " AND ".join(self._where_clauses)

        # 默认排序
        order_clauses = list(self._order_by_clauses)
        if not order_clauses and self._meta.ordering:
            for part in self._meta.ordering.split(","):
                part = part.strip()
                if part.startswith("-"):
                    order_clauses.append(f'"{part[1:]}" DESC')
                else:
                    order_clauses.append(f'"{part}"')
        if order_clauses:
            sql += " ORDER BY " + ", ".join(order_clauses)

        # LIMIT 和 OFFSET 不缓存（因为可能不同调用不同值）
        if self._limit_val is not None:
            sql += " LIMIT ?"
        if self._offset_val is not None:
            sql += " OFFSET ?"

        self._cached_sql = sql
        return sql

    def _build_count_sql(self) -> str:
        """构建 COUNT 查询 SQL（带缓存）。"""
        if self._cached_count_sql:
            return self._cached_count_sql

        sql = f'SELECT COUNT(*) FROM "{self._meta.table_name}"'
        if self._where_clauses:
            sql += " WHERE " + " AND ".join(self._where_clauses)
        self._cached_count_sql = sql
        return sql

    def _build_exists_sql(self) -> str:
        """构建 EXISTS 查询 SQL。"""
        return f"SELECT 1 FROM ({self._build_sql()}) LIMIT 1"

    def _build_params(self) -> List[Any]:
        """构建完整的参数列表（含 limit/offset）。"""
        params = list(self._params)
        if self._limit_val is not None:
            params.append(self._limit_val)
        if self._offset_val is not None:
            params.append(self._offset_val)
        return params

    def _row_to_model(self, row: sqlite3.Row):
        """将 sqlite3.Row 转换为模型实例、字典或元组。"""
        mode = self._values_mode

        if mode == 'flat':
            val = row[self._select_fields[0]]
            return _from_sql_value(val, self._meta.fields[self._select_fields[0]].py_type)

        if mode == 'tuple':
            return tuple(
                _from_sql_value(row[f], self._meta.fields[f].py_type)
                for f in self._select_fields
            )

        if mode == 'dict':
            return {
                f: _from_sql_value(row[f], self._meta.fields[f].py_type)
                for f in self._select_fields
            }

        # 默认返回模型实例
        model = self._model_cls.__new__(self._model_cls)
        model._exists = True
        model._meta.db = self._db
        for field_name in self._meta.field_names:
            value = row[field_name]
            py_type = self._meta.fields[field_name].py_type
            object.__setattr__(
                model, field_name, _from_sql_value(value, py_type)
            )
        return model

    def _execute(self) -> List:
        """执行查询，返回结果列表。"""
        cursor = self._db._execute(self._build_sql(), self._build_params())
        rows = cursor.fetchall()
        return [self._row_to_model(row) for row in rows]

    def _execute_first(self):
        """执行查询，仅返回第一个结果。"""
        cursor = self._db._execute(self._build_sql(), self._build_params())
        row = cursor.fetchone()
        if row:
            return self._row_to_model(row)
        return None

    def _get_one(self):
        """返回且仅返回一条结果。"""
        results = self._execute()
        if not results:
            raise NotFoundError(
                f"{self._model_cls.__name__}.objects.get() 未找到匹配记录"
            )
        if len(results) > 1:
            raise NotFoundError(
                f"{self._model_cls.__name__}.objects.get() 返回了多条结果 (共 {len(results)} 条)"
            )
        return results[0]

    def __iter__(self) -> Generator[_T, None, None]:
        """迭代查询结果。"""
        yield from self._execute()

    def __len__(self) -> int:
        """len(qs) 触发 COUNT 查询。"""
        return self.count()

    def __bool__(self) -> bool:
        """bool(qs) 检查是否存在记录。"""
        return self.exists()

    def __repr__(self) -> str:
        return (
            f"<QuerySet model={self._model_cls.__name__} "
            f"sql={self._build_sql()[:80]}>"
        )


# ──────────────────────────────────────────────
# Page - 分页结果
# ──────────────────────────────────────────────


class Page(Generic[_T]):
    """分页结果容器。"""

    __slots__ = ("items", "total", "page", "page_size", "pages")

    def __init__(
        self,
        items: List[_T],
        total: int,
        page: int,
        page_size: int,
        pages: int,
    ):
        self.items = items
        self.total = total
        self.page = page
        self.page_size = page_size
        self.pages = pages

    def __repr__(self) -> str:
        return (
            f"<Page page={self.page}/{self.pages} "
            f"total={self.total} items={len(self.items)}>"
        )

    def __bool__(self) -> bool:
        return len(self.items) > 0

    def __len__(self) -> int:
        return len(self.items)

    def has_previous(self) -> bool:
        """是否有上一页。"""
        return self.page > 1

    def has_next(self) -> bool:
        """是否有下一页。"""
        return self.page < self.pages


# ──────────────────────────────────────────────
# Manager - 模型管理器
# ──────────────────────────────────────────────


class Manager:
    """模型管理器，作为 QuerySet 的工厂，挂在 Model 子类上作为 objects 属性。

    用法：
        User.objects.filter(...).all()
    """

    def __init__(self):
        self._model_cls: Optional[Type[Model]] = None

    def __set_name__(self, owner: Type[Model], name: str):
        self._model_cls = owner

    def _get_db(self) -> "Database":
        """获取模型关联的数据库。"""
        db = self._model_cls._meta.db
        if db is None:
            raise ConnectionError(
                f"模型 {self._model_cls.__name__} 尚未关联数据库，"
                f"请先调用 Database.register()"
            )
        return db

    def get_queryset(self) -> QuerySet:
        """返回一个新的 QuerySet 实例。"""
        return QuerySet(self._model_cls, self._get_db())

    # ─── 委托给 QuerySet 的方法 ───

    def filter(self, _query: Optional[str] = None, **kwargs) -> QuerySet:
        return self.get_queryset().filter(_query, **kwargs)

    def exclude(self, **kwargs) -> QuerySet:
        return self.get_queryset().exclude(**kwargs)

    def limit(self, n: int) -> QuerySet:
        return self.get_queryset().limit(n)

    def offset(self, n: int) -> QuerySet:
        return self.get_queryset().offset(n)

    def order_by(self, *fields: str) -> QuerySet:
        return self.get_queryset().order_by(*fields)

    def all(self) -> List[Model]:
        return self.get_queryset().all()

    def first(self) -> Optional[Model]:
        return self.get_queryset().first()

    def get(self, **kwargs) -> Model:
        return self.get_queryset().get(**kwargs)

    def count(self) -> int:
        return self.get_queryset().count()

    def exists(self) -> bool:
        return self.get_queryset().exists()

    def iterator(self, batch_size: int = 1000) -> Generator[Model, None, None]:
        return self.get_queryset().iterator(batch_size)

    def update(self, **kwargs) -> int:
        return self.get_queryset().update(**kwargs)

    def delete(self) -> int:
        return self.get_queryset().delete()

    def values(self, *fields: str) -> QuerySet:
        return self.get_queryset().values(*fields)

    def values_list(self, *fields: str, flat: bool = False) -> QuerySet:
        return self.get_queryset().values_list(*fields, flat=flat)

    def paginate(self, page: int, page_size: int = 20) -> Page:
        return self.get_queryset().paginate(page, page_size)

    def in_bulk(self, id_list: List[Any], field_name: Optional[str] = None) -> Dict[Any, Model]:
        return self.get_queryset().in_bulk(id_list, field_name)

    def bulk_create(self, models: List[Model], batch_size: int = 500) -> List[Model]:
        """批量插入模型实例（性能远优于逐个 save）。

        Args:
            models: 模型实例列表
            batch_size: 每批插入数量

        Returns:
            插入后的模型列表（自动填充自增主键）
        """
        if not models:
            return models

        db = self._get_db()
        model_cls = self._model_cls
        table = model_cls._meta.table_name
        pk_name = model_cls._meta.pk_name
        field_names = model_cls._meta.field_names

        cols = [f for f in field_names]
        placeholders = ", ".join("?" for _ in cols)
        sql = f'INSERT INTO "{table}" ({", ".join(f'"{c}"' for c in cols)}) VALUES ({placeholders})'

        def model_to_row(m: Model) -> List[Any]:
            row = []
            for fname in field_names:
                val = getattr(m, fname, None)
                row.append(_to_sql_value(val))
            return row

        with db.transaction():
            for i in range(0, len(models), batch_size):
                batch = models[i : i + batch_size]
                rows = [model_to_row(m) for m in batch]
                cursor = db._executemany(sql, rows)
                # 填充自增主键（lastrowid 在 executemany 后可能为 None）
                if pk_name == "id" and cursor.lastrowid is not None:
                    base = cursor.lastrowid - len(batch) + 1
                    for j, m in enumerate(batch):
                        if getattr(m, pk_name, None) is None:
                            object.__setattr__(m, pk_name, base + j)
                for m in batch:
                    m._exists = True
                    m._meta.db = db

        return models


# ──────────────────────────────────────────────
# Database - 数据库连接管理器
# ──────────────────────────────────────────────


class Database:
    """SQLite3 数据库连接管理器。

    职责：
    - 管理连接生命周期（连接、关闭）
    - 自动启用 WAL 模式（提升并发读性能）
    - 提供事务上下文管理器
    - 管理模型注册与建表

    性能特性：
    - WAL 模式：写入不阻塞读取
    - synchronous = NORMAL：写入性能提升 2-3 倍
    - journal_size_limit：防止日志文件无限增长
    - cache_size：增加缓存减少磁盘 I/O

    用法：
        db = Database('data.db')
        db.register(User, Article)
        db.create_tables()

        with db.transaction():
            user.save()
    """

    def __init__(
        self,
        db_path: str,
        *,
        timeout: float = 5.0,
        cache_size: int = -8000,
        journal_size_limit: int = 67108864,
    ):
        """初始化数据库连接。

        Args:
            db_path: SQLite3 数据库文件路径。若文件不存在则自动创建。
            timeout: 连接超时时间（秒），默认 5 秒。
            cache_size: 页缓存大小（负数表示 KB），默认 8000KB。
            journal_size_limit: WAL 日志大小限制（字节），默认 64MB。
        """
        self._db_path = db_path
        self._timeout = timeout
        self._cache_size = cache_size
        self._journal_size_limit = journal_size_limit
        self._conn: Optional[sqlite3.Connection] = None
        self._models: Dict[str, Type[Model]] = {}

    # ─── 连接管理 ───

    def connect(self) -> "Database":
        """建立数据库连接并应用性能优化配置。

        线程安全：使用 check_same_thread=False 以允许跨线程使用，
        但调用方需确保同时对同一 Database 对象的访问是线程安全的。
        """
        if self._conn is not None:
            return self

        self._conn = sqlite3.connect(
            self._db_path,
            timeout=self._timeout,
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute(f"PRAGMA cache_size={self._cache_size}")
        self._conn.execute(f"PRAGMA journal_size_limit={self._journal_size_limit}")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA temp_store=MEMORY")
        self._conn.execute("PRAGMA mmap_size=268435456")  # 256MB mmap

        return self

    def close(self):
        """关闭数据库连接。

        关闭前先提交未完成的事务，确保数据持久化。
        """
        if self._conn:
            try:
                self._conn.commit()
            except Exception:
                pass
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    @property
    def is_connected(self) -> bool:
        """数据库是否已连接。"""
        return self._conn is not None

    @property
    def db_path(self) -> str:
        """数据库文件路径。"""
        return self._db_path

    # ─── 模型注册 ───

    def register(self, *models: Type[Model]) -> "Database":
        """注册模型到数据库。

        注册时将模型的 _meta.db 指向当前 Database 实例。
        每个模型都会获得独立的 objects 管理器（不继承父类的）。
        """
        self.connect()
        for model_cls in models:
            model_cls._meta.db = self
            self._models[model_cls._meta.table_name] = model_cls
            # 每个模型都创建独立的 Manager（不继承父类的）
            # 使用 __dict__ 检查避免父类的 objects 被错误复用
            if "objects" not in model_cls.__dict__:
                manager = Manager()
                manager._model_cls = model_cls
                model_cls.objects = manager
        return self

    def create_tables(self) -> "Database":
        """为所有已注册的模型创建数据库表（IF NOT EXISTS）。"""
        self.connect()
        for table_name, model_cls in self._models.items():
            self._create_table(model_cls)
        return self

    def drop_tables(self) -> "Database":
        """删除所有已注册模型对应的表。"""
        self.connect()
        for table_name, model_cls in reversed(list(self._models.items())):
            self._execute(f'DROP TABLE IF EXISTS "{table_name}"')
        return self

    def _create_table(self, model_cls: Type[Model]) -> None:
        """为单个模型创建表及其索引。"""
        meta = model_cls._meta
        columns = ",\n  ".join(
            field.to_ddl() for field in meta.fields.values()
        )
        sql = f'CREATE TABLE IF NOT EXISTS "{meta.table_name}" (\n  {columns}\n)'
        self._execute(sql)

        # 创建索引
        for field in meta.fields.values():
            index_ddl = field.to_index_ddl(meta.table_name)
            if index_ddl:
                self._execute(index_ddl)

    # ─── 事务管理 ───

    def transaction(self) -> "_TransactionContext":
        """返回事务上下文管理器。

        在 with 块内的所有数据库操作将在一个事务中执行。
        成功自动 COMMIT，异常自动 ROLLBACK。
        """
        return _TransactionContext(self)

    # ─── 原生 SQL 执行 ───

    def execute(self, sql: str, params: Optional[Sequence[Any]] = None) -> List[sqlite3.Row]:
        """执行原生 SQL 查询（自动连接）。

        Args:
            sql: SQL 语句
            params: 参数列表

        Returns:
            查询结果行列表（如果是查询语句）或空列表
        """
        self.connect()
        cursor = self._execute(sql, params or [])
        if sql.strip().upper().startswith(("SELECT", "PRAGMA", "EXPLAIN")):
            return cursor.fetchall()
        return []

    def _execute(self, sql: str, params: Optional[Sequence[Any]] = None) -> sqlite3.Cursor:
        """内部执行方法（无自动连接检查）。"""
        if self._conn is None:
            raise ConnectionError("数据库未连接，请先调用 connect()")
        try:
            return self._conn.execute(sql, params or [])
        except sqlite3.IntegrityError as e:
            raise IntegrityError(str(e)) from e
        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                raise ORMError(
                    f"表不存在，请确保已调用 create_tables(): {e}"
                ) from e
            raise ORMError(f"数据库操作失败: {e}") from e

    def _executemany(self, sql: str, params_list: Sequence[Sequence[Any]]) -> sqlite3.Cursor:
        """批量执行（用于 bulk_create）。"""
        if self._conn is None:
            raise ConnectionError("数据库未连接，请先调用 connect()")
        try:
            return self._conn.executemany(sql, params_list)
        except sqlite3.IntegrityError as e:
            raise IntegrityError(str(e)) from e
        except sqlite3.OperationalError as e:
            raise ORMError(f"数据库操作失败: {e}") from e

    def backup(self, target_path: str) -> "Database":
        """备份数据库到指定文件。

        策略（按优先顺序）：
        1. VACUUM INTO — 最快且无需额外连接
        2. WAL checkpoint + 文件复制 — 兼容性最好
        """
        self.connect()
        # 先触发 WAL checkpoint 确保数据一致性
        try:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        except Exception:
            pass
        # 尝试 VACUUM INTO（SQLite 3.27.0+）
        escaped = target_path.replace("'", "''")
        try:
            self._conn.execute(f"VACUUM INTO '{escaped}'")
            return self
        except sqlite3.OperationalError:
            pass
        # 回退：文件复制
        import shutil
        self._conn.commit()
        self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        shutil.copy2(self._db_path, target_path)
        return self

    def vacuum(self) -> "Database":
        """回收数据库未使用的空间。

        VACUUM 不能在事务内执行，因此先提交未完成的事务。
        """
        self.connect()
        self._conn.commit()
        self._conn.execute("VACUUM")
        return self

    # ─── 上下文管理器 ───

    def __enter__(self) -> "Database":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __repr__(self) -> str:
        return f"<Database path='{self._db_path}' connected={self.is_connected}>"


# ──────────────────────────────────────────────
# _TransactionContext - 事务上下文管理器
# ──────────────────────────────────────────────


class _TransactionContext:
    """事务上下文管理器，支持嵌套事务（自动使用 savepoint）。"""

    _local = threading.local()

    def __init__(self, db: Database):
        self._db = db
        self._savepoint_name: Optional[str] = None

    def __enter__(self):
        db = self._db
        db.connect()

        if not hasattr(_TransactionContext._local, "depth"):
            _TransactionContext._local.depth = 0
            _TransactionContext._local.conn = None

        if _TransactionContext._local.depth == 0:
            _TransactionContext._local.conn = db._conn
            db._conn.execute("BEGIN")
        else:
            # 嵌套事务使用 savepoint
            self._savepoint_name = f"sp_{_TransactionContext._local.depth}"
            db._conn.execute(f"SAVEPOINT {self._savepoint_name}")

        _TransactionContext._local.depth += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        _TransactionContext._local.depth -= 1
        conn = _TransactionContext._local.conn

        try:
            if exc_type is None:
                if self._savepoint_name:
                    conn.execute(f"RELEASE {self._savepoint_name}")
                else:
                    conn.execute("COMMIT")
            else:
                if self._savepoint_name:
                    conn.execute(f"ROLLBACK TO {self._savepoint_name}")
                else:
                    conn.execute("ROLLBACK")
        finally:
            if _TransactionContext._local.depth == 0:
                _TransactionContext._local.conn = None

        return False  # 不抑制异常


# ──────────────────────────────────────────────
# 便利导出
# ──────────────────────────────────────────────

class _FieldsNamespace:
    """提供类似于 django.db.models 的字段命名空间。"""

    CharField = CharField
    TextField = TextField
    IntegerField = IntegerField
    FloatField = FloatField
    BooleanField = BooleanField
    DateTimeField = DateTimeField
    BlobField = BlobField
    Field = Field


# fields 命名空间实例，方便用户通过 fields.XXXField 访问
fields = _FieldsNamespace()

__all__ = [
    "Database",
    "Model",
    "Manager",
    "QuerySet",
    "Page",
    "fields",
    # 字段类
    "Field",
    "CharField",
    "TextField",
    "IntegerField",
    "FloatField",
    "BooleanField",
    "DateTimeField",
    "BlobField",
    # 异常
    "ORMError",
    "ConnectionError",
    "IntegrityError",
    "NotFoundError",
    "FieldError",
]
