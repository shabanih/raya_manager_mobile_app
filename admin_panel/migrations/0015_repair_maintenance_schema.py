
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('admin_panel', '0014_maintenance_receiver_renter_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                """
                ALTER TABLE admin_panel_maintenance
                ADD COLUMN receiver_renter_id bigint NULL
                REFERENCES user_app_renter(id)
                DEFERRABLE INITIALLY DEFERRED
                """,
                """
                ALTER TABLE admin_panel_maintenance
                ADD COLUMN receiver_type varchar(20) NULL
                """,
                """
                ALTER TABLE admin_panel_maintenance
                ADD COLUMN unit_id bigint NULL
                REFERENCES user_app_unit(id)
                DEFERRABLE INITIALLY DEFERRED
                """,
                """
                CREATE INDEX admin_panel_maintenance_receiver_renter_id_f629fa02
                ON admin_panel_maintenance(receiver_renter_id)
                """,
                """
                CREATE INDEX admin_panel_maintenance_unit_id_46e6b600
                ON admin_panel_maintenance(unit_id)
                """,
                """
                CREATE TABLE admin_panel_thirdparty (
                    id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                    name varchar(200) NOT NULL,
                    person_type varchar(20) NOT NULL DEFAULT 'person',
                    mobile varchar(20) NULL,
                    description varchar(500) NULL,
                    is_active bool NOT NULL DEFAULT 1,
                    created_at datetime NOT NULL,
                    house_id bigint NOT NULL
                    REFERENCES user_app_myhouse(id)
                    DEFERRABLE INITIALLY DEFERRED,
                    CONSTRAINT unique_third_party_name_per_house
                    UNIQUE (house_id, name)
                )
                """,
                """
                CREATE INDEX admin_panel_thirdparty_house_id_6289a1a7
                ON admin_panel_thirdparty(house_id)
                """,
                """
                ALTER TABLE admin_panel_maintenance
                ADD COLUMN receiver_third_party_id bigint NULL
                REFERENCES admin_panel_thirdparty(id)
                DEFERRABLE INITIALLY DEFERRED
                """,
                """
                CREATE INDEX admin_panel_maintenance_receiver_third_party_id_ef74b833
                ON admin_panel_maintenance(receiver_third_party_id)
                """,
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
