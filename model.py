from pynamodb.models import Model
from pynamodb.attributes import UnicodeAttribute

class Monster(Model):
    class Meta:
        table_name = 'beastforge-monsters'
        region = 'us-west-2'

    id = UnicodeAttribute(hash_key=True)
    name = UnicodeAttribute()

