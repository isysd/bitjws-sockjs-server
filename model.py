import sqlalchemy as sa
import sqlalchemy.orm as orm
from sqlalchemy_login_models.model import Base, User, UserKey as ParentUserKey

__all__ = ['User', 'UserKey', 'Coin']


class UserKey(ParentUserKey):
    """A User's API key extended with a get_owner function."""

    def get_owner(self):
        return self.user_id


class Coin(Base):
    """A Coin for someone's collection."""

    __tablename__ = "coin"
    __name__ = "coin"

    id = sa.Column(sa.Integer, primary_key=True, doc="primary key")
    metal = sa.Column(sa.String(255), nullable=False)
    mint = sa.Column(sa.String(255), nullable=False)

    user_id = sa.Column(
        sa.Integer,
        sa.ForeignKey('user.id'),
        nullable=False)
    user = orm.relationship("User", foreign_keys=['user_id'])

    def __init__(self, metal, mint, uid):
        self.metal = metal
        self.mint = mint
        self.user_id = uid

    def get_owner(self):
        return self.user_id
