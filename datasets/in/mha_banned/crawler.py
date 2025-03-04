import re
import csv
from lxml import html
from typing import List, Dict
from normality import collapse_spaces
from pantomime.types import HTML, CSV

from zavod import Context
from zavod import helpers as h

SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTc-EkLWZgLKDPVvcrCoKLp17EEo535uP1EMcLKFl_b6T3z6Tq99BrI3R9GhxKirgRoozND1xQ48O4-/pub?output=csv"

CLEAN = [
    ", all its formations and front organizations.",
    ", all its formations and front organizations",
    ", All its formations and front organizations",
    ", All its formations and Front Organisations",
    "all its formations and front organizations.",
    ", and all its Manifestations",
]
REGEX_PERSON_PREFIX = re.compile(r"^\d+\.")

def parse_names(field: str) -> List[str]:
    names: List[str] = []
    for value in field.split(';'):
        value = value.strip()
        if len(value):
            names.append(value)
    return names

def crawl_sheet(context: Context):
    path = context.fetch_resource("accommodations.csv", SHEET_URL)
    context.export_resource(path, CSV, title=context.SOURCE_TITLE)
    named_ids: Dict[str, str] = {}
    with open(path, "r") as fh:
        for row in csv.DictReader(fh):
            entity = context.make(row.pop("Type", "LegalEntity"))
            source_url = row.pop("SourceURL")
            id_ = row.pop("ID")
            name = row.pop("Name")
            if name is None:
                context.log.warn("No name", row=row)
                continue
            entity.id = context.make_id(id_, name, source_url)
            assert entity.id is not None, row
            named_ids[name] = entity.id
            entity.add('name', name)
            entity.add('notes', row.pop("Notes"))
            entity.add("topics", "sanction")
            entity.add("sourceUrl", source_url)
            entity.add("alias", parse_names(row.pop("Aliases")))
            entity.add("weakAlias", parse_names(row.pop("Weak")))

            sanction = h.make_sanction(context, entity, id_)
            sanction.add('program', row.pop("Designation"))
            sanction.add('authorityId', id_)

            linked = row.pop("Linked", "").strip()
            if len(linked) and linked in named_ids:
                rel = context.make("UnknownLink")
                rel.id = context.make_id(linked, "linked", entity.id)
                rel.add("subject", named_ids[linked])
                rel.add("object", entity.id)
                context.emit(rel)
            
            context.emit(entity, target=True)
            context.emit(sanction)


def crawl(context: Context):
    crawl_sheet(context)
    path = context.fetch_resource(
         "organisations.html",
         context.data_url + "banned-organisations",
    #     headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "},
    )
    context.export_resource(path, HTML)
    context.export_resource(path, HTML, title="Banned organisations")
    with open(path, "rb") as fh:
        doc = html.fromstring(fh.read())
    for row in doc.findall('.//div[@class="field-content"]//table//tr'):
        cells = [c.text for c in row.findall("./td")]
        if len(cells) != 2:
            continue
        serial, name = cells
        if "Organisations listed in the Schedule" in name:
            continue
        entity = context.make("Organization")
        entity.id = context.make_id(serial, name)
        entity.add("topics", "sanction")
        for alias in name.split("/"):
            for clean in CLEAN:
                alias = alias.replace(clean, " ")
            entity.add("name", collapse_spaces(alias))

        context.emit(entity, target=True)

    people_url = context.data_url + "page/individual-terrorists-under-uapa"
    people_path = context.fetch_resource("individuals.html", people_url)
    context.export_resource(people_path, HTML, "Individuals under UAPA")
    with open(people_path, "rb") as fh:
        doc = html.fromstring(fh.read())
    doc.make_links_absolute(people_url)
    for para in doc.findall(".//p"):
        line = collapse_spaces(para.text_content())
        if not line:
            continue
        if not REGEX_PERSON_PREFIX.match(line):
            context.log.warn("Couldn't parse item", item=line)
            continue
        names = REGEX_PERSON_PREFIX.sub("", line)
        names = re.sub(r"\.$", "", names)
        name_list = [n.strip() for n in names.split("@")]
        entity = context.make("Person")
        entity.id = context.make_id(names)
        entity.add("name", name_list.pop(0))
        if name_list:
            entity.add("alias", name_list)
        entity.add("topics", "sanction")
        entity.add("sourceUrl", para.find(".//a").get("href"))
        context.emit(entity, target=True)