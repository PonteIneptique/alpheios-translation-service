""" Tests here that reuse subscripts such as function from atservices.scripts.collatinus should
just check that these function are called, not that they have the right effect. Checking the effects of these
function should be done in their respective test modules (see .test_collatinus)

"""
import os

from unittest import TestCase
from click.testing import CliRunner
from mock import patch
from sqlalchemy.exc import OperationalError

from atservices import create_app
from atservices.scripts import (
    make_data_survey_cli,
    make_db_cli,
    make_data_cli
)
from atservices.models import Translation


from ..fixtures import insert_misses


class TestDataScript(TestCase):
    """ Tests for the Data Scripts
     """

    def setUp(self):
        self.app, self.db = create_app("test")

        self.cli = make_data_cli(db=self.db)
        make_db_cli(cli=self.cli, db=self.db)
        make_data_survey_cli(cli=self.cli, db=self.db)

        self.runner = CliRunner()

    def invoke(self, commands):
        return self.runner.invoke(self.cli, commands)

    @patch("atservices.scripts.check_collatinus_corpora", return_value=True)
    @patch("atservices.scripts.download_collatinus_corpora")
    def test_data_download_when_downloaded(self, collatinus_download, check_collatinus):
        """ Test that data download do not force download if not asked to """
        self.invoke(["data-download"])
        check_collatinus.assert_called()
        collatinus_download.assert_not_called()

    @patch("atservices.scripts.check_collatinus_corpora", return_value=True)
    @patch("atservices.scripts.download_collatinus_corpora")
    def test_data_download_when_force(self, collatinus_download, check_collatinus):
        """ Test that data download do force download"""
        self.invoke(["data-download", "--force"])
        # We do not check check_collatinus because it might change in order.
        # Most important thing is : collatinus downloads
        collatinus_download.assert_called()

    @patch("atservices.scripts.check_collatinus_corpora", return_value=False)
    @patch("atservices.scripts.download_collatinus_corpora")
    def test_data_download_when_not_downloaded(self, collatinus_download, check_collatinus):
        """ Test that data download are downloaded when data are not available """
        self.invoke(["data-download"])
        check_collatinus.assert_called()
        collatinus_download.assert_called()

    @patch("atservices.scripts.ingest_collatinus_corpora")
    def test_data_ingest(self, collatinus_ingest):
        """ Test that data ingest calls the right scripts """
        self.invoke(["data-ingest"])
        collatinus_ingest.assert_called()


class TestDBScript(TestCase):
    """ Tests for the modele Translation

    """

    def clear_db(self, app, db):
        with app.app_context():
            try:
                db.drop_all()
            except:
                pass

    def setUp(self):
        self.app, self.db = create_app("test")
        self.clear_db(self.app, self.db)

        # We create all cli to check that it does not overwrite anything
        with self.app.app_context():
            self.cli = make_data_cli(db=self.db)
            make_db_cli(cli=self.cli, db=self.db)
            make_data_survey_cli(cli=self.cli, db=self.db)

        self.runner = CliRunner()

    def tearDown(self):
        self.clear_db(self.app, self.db)
        del self.app
        del self.db

    def invoke(self, commands):
        return self.runner.invoke(self.cli, commands)

    def test_db_create(self):
        """ Test that db is created """
        with self.app.app_context():
            result = self.invoke(["db-create"])

        self.assertIn(
            "Creating database",
            result.output
        )
        with self.app.app_context():
            self.db.session.add(Translation(
                lemma="a", translation_lang="eng",
                lemma_lang="fre", translation="b"
            ))
            self.db.session.commit()

            self.assertEqual(
                len(Translation.query.all()), 1,
                "There should have been an insert"
            )

    def test_db_drop(self):
        """ Test that db is dropped """
        with self.app.app_context():
            self.db.create_all()

        with self.app.app_context():
            result = self.invoke(["db-drop"])

            self.assertIn("Dropping database", result.output)

        with self.assertRaises(OperationalError):
            with self.app.app_context():
                self.db.session.add(Translation(
                    lemma="a", translation_lang="eng",
                    lemma_lang="fre", translation="b"
                ))
                self.db.session.commit()

                self.assertEqual(
                    len(Translation.query.all()), 1,
                    "There should have been an insert"
                )

    def test_db_recreate(self):
        """ Test that db is recreated """
        with self.app.app_context():
            result = self.invoke(["db-create"])

        with self.app.app_context():
            self.db.session.add(Translation(
                lemma="a", translation_lang="eng",
                lemma_lang="fre", translation="b"
            ))
            self.db.session.commit()

            self.assertEqual(
                len(Translation.query.all()), 1,
                "There should have been an insert"
            )
        self.assertIn("Creating database", result.output)

        with self.app.app_context():
            result = self.invoke(["db-recreate"])

            self.assertIn(
                "Recreating the database",
                result.output
            )

        with self.app.app_context():
            self.assertEqual(
                len(Translation.query.all()), 0,
                "There should have been 0 insert"
            )


class TestSurveyScript(TestCase):
    """ Tests for the Survey Scripts
     """

    def setUp(self):
        self.app, self.db = create_app("test")

        self.cli = make_data_cli(db=self.db)
        make_db_cli(cli=self.cli, db=self.db)
        make_data_survey_cli(cli=self.cli, db=self.db)

        self.runner = CliRunner()

        with self.app.app_context():
            self.db.create_all()
            self.db.session.commit()

            insert_misses(self.db)

    def tearDown(self):
        with self.app.app_context():
            self.db.drop_all()

    def invoke(self, commands):
        with self.app.app_context():
            return self.runner.invoke(self.cli, commands)

    def test_dump(self):
        """ Test that dumping to CSV works """
        with self.runner.isolated_filesystem() as fs:

            self.invoke(["survey-dump"])

            with open(os.path.join(fs, "misses.csv")) as f:
                self.assertEqual(
                    f.read(),
                    """at	lemma	lemma_lang	translation_lang	client
2018-01-01 19:00:00	lascivus	lat	fre	Collatinus-Lemmatize
2018-01-01 20:00:00	appétit	fre	eng	Bocuse
2018-01-01 21:00:00	bbq	eng	fre	They"""
                )

    def test_dump_specific_file(self):
        """ Test that dumping to CSV works with a specified filename """
        with self.runner.isolated_filesystem() as fs:

            self.invoke(["survey-dump", "--dest", "fake.csv"])

            with open(os.path.join(fs, "fake.csv")) as f:
                self.assertEqual(
                    f.read(),
                    """at	lemma	lemma_lang	translation_lang	client
2018-01-01 19:00:00	lascivus	lat	fre	Collatinus-Lemmatize
2018-01-01 20:00:00	appétit	fre	eng	Bocuse
2018-01-01 21:00:00	bbq	eng	fre	They"""
                )

    def test_clear(self):
        """ Test that clearing Misses works"""
        with self.runner.isolated_filesystem() as fs:

            self.invoke(["survey-clear"])
            self.invoke(["survey-dump"])

            with open(os.path.join(fs, "misses.csv")) as f:
                self.assertEqual(
                    f.read(),
                    """at	lemma	lemma_lang	translation_lang	client"""
                )

    def test_clear_until(self):
        """ Test that clearing Misses until a specific datetime works"""
        with self.runner.isolated_filesystem() as fs:

            self.invoke(["survey-clear", '--until', '"2018-01-01 19:59:00"'])
            self.invoke(["survey-dump"])

            with open(os.path.join(fs, "misses.csv")) as f:
                self.assertEqual(
                    f.read(),
                    """at	lemma	lemma_lang	translation_lang	client
2018-01-01 20:00:00	appétit	fre	eng	Bocuse
2018-01-01 21:00:00	bbq	eng	fre	They"""
                )