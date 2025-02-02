import datetime

import ujson as json
from sqlalchemy import create_engine, Column, Text, TIMESTAMP, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from tenacity import retry, stop_after_attempt

Base = declarative_base()

DB_LINK = 'sqlite:///database/local.db'


class DirtyFilterTable(Base):
    __tablename__ = "filter_cache"
    desc = Column(Text, primary_key=True)
    result = Column(Text)
    timestamp = Column(TIMESTAMP, default=text('CURRENT_TIMESTAMP'))


class LocalDBSession:
    def __init__(self):
        self.engine = engine = create_engine(DB_LINK)
        Base.metadata.create_all(bind=engine, checkfirst=True)
        self.Session = sessionmaker()
        self.Session.configure(bind=self.engine)

    @property
    def session(self):
        return self.Session()


session = LocalDBSession().session


def auto_rollback_error(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            session.rollback()
            raise e

    return wrapper


class DirtyWordCache:
    @retry(stop=stop_after_attempt(3))
    @auto_rollback_error
    def __init__(self, query_word):
        self.query_word = query_word
        self.query = session.query(DirtyFilterTable).filter_by(desc=self.query_word).first()
        self.need_insert = False
        if self.query is None:
            self.need_insert = True
        if self.query is not None and datetime.datetime.now().timestamp() - self.query.timestamp.timestamp() > 86400:
            session.delete(self.query)
            session.commit()
            self.need_insert = True

    @retry(stop=stop_after_attempt(3))
    @auto_rollback_error
    def update(self, result: dict):
        session.add_all([DirtyFilterTable(desc=self.query_word, result=json.dumps(result))])
        session.commit()

    def get(self):
        if not self.need_insert:
            return json.loads(self.query.result)
        else:
            return False
