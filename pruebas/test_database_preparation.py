import pruebas  # Permite importar app y bd al ejecutar desde la raíz.
"""Prueba el SQL de creación en tablas desechables, sin tocar las de la aplicación."""
import unittest
from uuid import uuid4

from sqlalchemy import inspect

from bd.conexion import engine
from bd.preparar import SQL


class TestDatabasePreparation(unittest.TestCase):
    def test_create_tables_twice(self):
        suffix = uuid4().hex[:12]
        participants = 'ballers_test_participants_' + suffix
        logos = 'ballers_test_logos_' + suffix
        statements = []
        for statement in SQL:
            statement = statement.replace('participant_logos', logos)
            statement = statement.replace('participants', participants)
            statement = statement.replace('fk_logos_participant', 'fk_ballers_test_' + suffix)
            statements.append(statement)
        with engine.begin() as connection:
            try:
                # La segunda ejecución debe conservar las tablas ya creadas.
                for repetition in range(2):
                    for statement in statements:
                        connection.exec_driver_sql(statement)
                inspector = inspect(connection)
                self.assertEqual(inspector.get_pk_constraint(logos)['constrained_columns'], ['participant_id'])
                foreign_key = inspector.get_foreign_keys(logos)[0]
                self.assertEqual(foreign_key['referred_table'], participants)
                self.assertEqual(foreign_key['options']['ondelete'], 'CASCADE')
                self.assertTrue(any(key['column_names'] == ['nick'] for key in inspector.get_unique_constraints(participants)))
            finally:
                # Los nombres se generan aquí y nunca proceden del usuario.
                connection.exec_driver_sql('DROP TABLE IF EXISTS ' + logos)
                connection.exec_driver_sql('DROP TABLE IF EXISTS ' + participants)
