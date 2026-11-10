"""Golden tests for the deterministic formatters (examples follow the published style guides)."""
from app.citation.common import missing_fields, parse_name
from app.citation.engine import cite, normalise_metadata


def forms(metadata, style, pinpoint=None):
    out = cite(normalise_metadata(metadata), style, pinpoint)["forms"]
    return {key: value["text"] for key, value in out.items()}


def html(metadata, style, form="footnote", pinpoint=None):
    return cite(normalise_metadata(metadata), style, pinpoint)["forms"][form]["html"]


BOOK = {"type": "book", "title": "Administrative Law", "authors": ["Timothy Endicott"], "edition": "4", "publisher": "Oxford University Press", "year": "2018"}
ARTICLE = {"type": "article", "title": "Theory, “Pure Theory” and Values in Public Law", "authors": [{"given": "Paul", "family": "Craig"}], "journal": "PL", "year": "2005", "pages": "440-447"}
ARTICLE_VOL = {"type": "article", "title": "The Rule of Law and Its Virtue", "authors": ["Joseph Raz"], "journal": "Law Quarterly Review", "volume": "93", "issue": "2", "year": "1977", "pages": "195–211", "doi": "10.1000/xyz"}
DONOGHUE = {"type": "case", "title": "Donoghue v Stevenson", "report_citation": "[1932] AC 562", "court": "HL", "year": "1932"}
CORR = {"type": "case", "title": "Corr v IBC Vehicles Ltd", "neutral_citation": "[2008] UKHL 13", "report_citation": "[2008] 1 AC 884", "court": "HL"}
BROWN = {"type": "case", "title": "Brown v. Board of Education", "report_citation": "347 US 483", "court": "Supreme Court of the United States", "year": "1954"}
VCLT = {"type": "treaty", "title": "Vienna Convention on the Law of Treaties", "adopted_date": "1969-05-23", "entry_into_force_date": "1980-01-27", "treaty_series": "1155 UNTS 331", "short_title": "VCLT"}
HRA = {"type": "legislation", "title": "Human Rights Act 1998", "year": "1998", "jurisdiction": "UK"}
CHAPTER = {"type": "chapter", "title": "The Value of Authorship in the Digital Environment", "authors": ["Justine Pila"], "editors": ["William H Dutton", "Paul W Jeffreys"], "container_title": "World Wide Research: Reshaping the Sciences and Humanities in the Century of Information", "publisher": "MIT Press", "year": "2010", "pages": "210-231"}


class TestOscola:
    def test_book(self):
        f = forms(BOOK, "oscola", {"kind": "page", "value": "45"})
        assert f["full"] == "Timothy Endicott, Administrative Law (4th edn, OUP 2018)"
        assert f["footnote"] == "Timothy Endicott, Administrative Law (4th edn, OUP 2018) 45."
        assert f["bibliography"] == "Endicott T, Administrative Law (4th edn, OUP 2018)"
        assert f["short"] == "Endicott (n #) 45."
        assert "<i>Administrative Law</i>" in html(BOOK, "oscola")

    def test_article_without_volume_uses_square_brackets(self):
        f = forms(ARTICLE, "oscola", {"kind": "page", "value": "442"})
        assert f["footnote"] == "Paul Craig, ‘Theory, “Pure Theory” and Values in Public Law’ [2005] PL 440, 442."
        assert f["bibliography"] == "Craig P, ‘Theory, “Pure Theory” and Values in Public Law’ [2005] PL 440"

    def test_article_with_volume(self):
        assert forms(ARTICLE_VOL, "oscola")["full"] == "Joseph Raz, ‘The Rule of Law and Its Virtue’ (1977) 93(2) Law Quarterly Review 195"

    def test_case_report_only(self):
        f = forms(DONOGHUE, "oscola", {"kind": "page", "value": "580"})
        assert f["footnote"] == "Donoghue v Stevenson [1932] AC 562 (HL) 580."
        assert f["short"] == "Donoghue (n #) 580."
        assert html(DONOGHUE, "oscola").startswith("<i>Donoghue v Stevenson</i> [1932]")
        # Tables of cases are not italicised
        assert "<i>" not in html(DONOGHUE, "oscola", "bibliography")

    def test_case_neutral_citation_and_paragraph(self):
        f = forms(CORR, "oscola", {"kind": "para", "value": "11"})
        assert f["footnote"] == "Corr v IBC Vehicles Ltd [2008] UKHL 13, [2008] 1 AC 884 [11]."

    def test_unreported_case(self):
        m = {"type": "case", "title": "Balogh v Hungary", "case_number": "App no 47940/99", "court": "ECtHR", "date": "2004-07-20"}
        assert forms(m, "oscola")["full"] == "Balogh v Hungary App no 47940/99 (ECtHR, 20 July 2004)"

    def test_us_case(self):
        assert forms(BROWN, "oscola")["full"] == "Brown v Board of Education 347 US 483 (1954)"

    def test_treaty(self):
        f = forms(VCLT, "oscola", {"kind": "article", "value": "31"})
        assert f["footnote"] == "Vienna Convention on the Law of Treaties (adopted 23 May 1969, entered into force 27 January 1980) 1155 UNTS 331 (VCLT) art 31."
        assert f["short"] == "VCLT (n #) art 31."

    def test_legislation(self):
        assert forms(HRA, "oscola", {"kind": "section", "value": "15(1)(b)"})["footnote"] == "Human Rights Act 1998, s 15(1)(b)."

    def test_chapter(self):
        assert forms(CHAPTER, "oscola")["full"] == (
            "Justine Pila, ‘The Value of Authorship in the Digital Environment’ in William H Dutton and Paul W Jeffreys (eds), "
            "World Wide Research: Reshaping the Sciences and Humanities in the Century of Information (MIT Press 2010)"
        )

    def test_more_than_three_authors(self):
        m = {**BOOK, "authors": ["A One", "B Two", "C Three", "D Four"]}
        assert forms(m, "oscola")["full"].startswith("A One and others, ")

    def test_initials_lose_full_stops(self):
        m = {"type": "book", "title": "The Concept of Law", "authors": ["H. L. A. Hart"], "edition": "2", "publisher": "Clarendon Press", "year": "1994"}
        f = forms(m, "oscola")
        assert f["full"] == "HLA Hart, The Concept of Law (2nd edn, Clarendon Press 1994)"
        assert f["bibliography"].startswith("Hart HLA, ")

    def test_website_and_thesis(self):
        site = {"type": "website", "title": "Virtual Friend Fires Employee", "authors": ["Sarah Cole"], "website": "Naked Law", "date": "2009-05-01", "url": "http://www.nakedlaw.com/2009/05/index.html", "accessed": "2009-11-19"}
        assert forms(site, "oscola")["full"] == "Sarah Cole, ‘Virtual Friend Fires Employee’ (Naked Law, 1 May 2009) <http://www.nakedlaw.com/2009/05/index.html> accessed 19 November 2009"
        thesis = {"type": "thesis", "title": "Injunctive Relief for Wrongful Termination of Employment", "authors": ["Javan Herberg"], "thesis_type": "DPhil thesis", "institution": "University of Oxford", "year": "1989"}
        assert forms(thesis, "oscola")["full"] == "Javan Herberg, ‘Injunctive Relief for Wrongful Termination of Employment’ (DPhil thesis, University of Oxford 1989)"


class TestBluebook:
    def test_book_small_caps(self):
        f = forms(BOOK, "bluebook", {"kind": "page", "value": "45"})
        assert f["footnote"] == "Timothy Endicott, Administrative Law 45 (4th ed. 2018)."
        assert '<span class="sc">Timothy Endicott</span>' in html(BOOK, "bluebook")
        assert f["short"] == "Endicott, supra note #, at 45."

    def test_edition_ordinals(self):
        assert "(3d ed. 2013)" in forms({**BOOK, "edition": "3rd", "year": "2013"}, "bluebook")["full"]

    def test_article(self):
        f = forms(ARTICLE_VOL, "bluebook", {"kind": "page", "value": "200"})
        assert f["footnote"] == "Joseph Raz, The Rule of Law and Its Virtue, 93 Law Quarterly Review 195, 200 (1977)."

    def test_us_case(self):
        f = forms(BROWN, "bluebook", {"kind": "page", "value": "495"})
        assert f["footnote"] == "Brown v. Board of Education, 347 U.S. 483, 495 (1954)."
        assert f["short"] == "Brown, 347 U.S. at 495."

    def test_uk_case(self):
        assert forms(DONOGHUE, "bluebook")["full"] == "Donoghue v. Stevenson, [1932] AC 562 (HL)"

    def test_treaty(self):
        f = forms(VCLT, "bluebook", {"kind": "article", "value": "31"})
        assert f["footnote"] == "Vienna Convention on the Law of Treaties art. 31, May 23, 1969, 1155 U.N.T.S. 331."


class TestApa:
    def test_book(self):
        f = forms(BOOK, "apa", {"kind": "page", "value": "45"})
        assert f["full"] == "Endicott, T. (2018). Administrative Law (4th ed.). Oxford University Press."
        assert f["footnote"] == "(Endicott, 2018, p. 45)"
        assert f["short"] == "Endicott (2018, p. 45)"

    def test_article(self):
        f = forms(ARTICLE_VOL, "apa")
        assert f["full"] == "Raz, J. (1977). The Rule of Law and Its Virtue. Law Quarterly Review, 93(2), 195–211. https://doi.org/10.1000/xyz"
        assert "<i>Law Quarterly Review</i>, <i>93</i>(2)" in html(ARTICLE_VOL, "apa", "full")

    def test_chapter_and_two_authors(self):
        f = forms(CHAPTER, "apa")
        assert f["full"].startswith("Pila, J. (2010). The Value of Authorship in the Digital Environment. In W. H. Dutton & P. W. Jeffreys (Eds.), World Wide Research")
        assert "(pp. 210–231). MIT Press." in f["full"]
        two = {**BOOK, "authors": ["Ann Smith", "Bob Jones"]}
        assert forms(two, "apa")["full"].startswith("Smith, A., & Jones, B. (2018).")
        assert forms(two, "apa")["footnote"] == "(Smith & Jones, 2018)"

    def test_case(self):
        f = forms(BROWN, "apa")
        assert f["full"] == "Brown v. Board of Education, 347 U.S. 483 (1954)."
        assert f["footnote"] == "(Brown v. Board of Education, 1954)"


class TestNoFabrication:
    def test_missing_details_are_omitted_and_reported(self):
        m = normalise_metadata({"type": "book", "title": "The Law of Treaties"})
        f = forms(m, "oscola")
        assert f["full"] == "The Law of Treaties"
        assert missing_fields(m)["required"] == ["Author or Editor", "Publisher", "Year"]

    def test_partial_article(self):
        m = {"type": "article", "title": "Untitled Draft", "authors": ["Ann Smith"]}
        assert forms(m, "oscola")["full"] == "Ann Smith, ‘Untitled Draft’"
        assert forms(m, "bluebook")["full"] == "Ann Smith, Untitled Draft"
        assert forms(m, "apa")["full"] == "Smith, A. (n.d.). Untitled Draft."

    def test_every_type_and_style_tolerates_empty_metadata(self):
        from app.citation.common import SOURCE_TYPES
        for kind in SOURCE_TYPES:
            for style in ("oscola", "bluebook", "apa"):
                for pin in (None, {"kind": "para", "value": "3"}):
                    out = forms({"type": kind, "title": "X"}, style, pin)
                    assert all("None" not in v and "()" not in v and "  " not in v for v in out.values()), (kind, style, out)


def test_parse_name():
    assert parse_name("Aust, Anthony") == {"family": "Aust", "given": "Anthony"}
    assert parse_name("Anthony Aust") == {"given": "Anthony", "family": "Aust"}
    assert parse_name("Ludwig van Beethoven") == {"given": "Ludwig", "family": "van Beethoven"}
