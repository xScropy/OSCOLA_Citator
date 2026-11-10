"use client";

import type { Metadata, Person } from "@/lib/types";
import { TYPE_LABELS } from "@/lib/types";

type Field = { key: string; label: string; placeholder?: string; wide?: boolean; hint?: string };

const DATE_HINT = "YYYY-MM-DD";

const FIELDS: Record<string, Field[]> = {
  case: [
    { key: "title", label: "Case name", placeholder: "Donoghue v Stevenson", wide: true },
    { key: "neutral_citation", label: "Neutral citation", placeholder: "[2008] UKHL 13" },
    { key: "report_citation", label: "Law report citation", placeholder: "[1932] AC 562" },
    { key: "court", label: "Court or tribunal", placeholder: "HL" },
    { key: "date", label: "Judgment date", placeholder: DATE_HINT },
    { key: "year", label: "Year" },
    { key: "case_number", label: "Case or application number", placeholder: "App no 47940/99" },
    { key: "jurisdiction", label: "Jurisdiction" },
    { key: "url", label: "Official URL", wide: true },
  ],
  legislation: [
    { key: "title", label: "Title", placeholder: "Human Rights Act 1998", wide: true },
    { key: "year", label: "Year" },
    { key: "jurisdiction", label: "Jurisdiction", placeholder: "UK" },
    { key: "number", label: "Act or regulation number", placeholder: "c 42" },
    { key: "url", label: "URL", wide: true },
  ],
  treaty: [
    { key: "title", label: "Official treaty title", wide: true },
    { key: "short_title", label: "Short title", placeholder: "VCLT" },
    { key: "treaty_series", label: "Treaty series reference", placeholder: "1155 UNTS 331" },
    { key: "adopted_date", label: "Adoption date", placeholder: DATE_HINT },
    { key: "entry_into_force_date", label: "Entry-into-force date", placeholder: DATE_HINT },
    { key: "url", label: "Official source URL", wide: true },
  ],
  book: [
    { key: "title", label: "Title", wide: true },
    { key: "edition", label: "Edition", placeholder: "3" },
    { key: "year", label: "Year" },
    { key: "publisher", label: "Publisher" },
    { key: "place", label: "Place of publication" },
    { key: "isbn", label: "ISBN" },
    { key: "doi", label: "DOI" },
  ],
  chapter: [
    { key: "title", label: "Chapter title", wide: true },
    { key: "container_title", label: "Book title", wide: true },
    { key: "edition", label: "Edition" },
    { key: "year", label: "Year" },
    { key: "publisher", label: "Publisher" },
    { key: "pages", label: "Pages", placeholder: "210-231" },
    { key: "isbn", label: "ISBN" },
    { key: "doi", label: "DOI" },
  ],
  article: [
    { key: "title", label: "Article title", wide: true },
    { key: "journal", label: "Journal", wide: true },
    { key: "year", label: "Year" },
    { key: "volume", label: "Volume" },
    { key: "issue", label: "Issue" },
    { key: "pages", label: "Pages", placeholder: "440-447" },
    { key: "doi", label: "DOI" },
    { key: "url", label: "URL" },
  ],
  report: [
    { key: "title", label: "Title", wide: true },
    { key: "number", label: "Report or paper number", placeholder: "Law Com No 313" },
    { key: "year", label: "Year" },
    { key: "publisher", label: "Publisher or institution" },
    { key: "doi", label: "DOI" },
    { key: "url", label: "URL", wide: true },
    { key: "accessed", label: "Access date", placeholder: DATE_HINT },
  ],
  thesis: [
    { key: "title", label: "Title", wide: true },
    { key: "thesis_type", label: "Thesis type", placeholder: "PhD thesis" },
    { key: "institution", label: "Institution" },
    { key: "year", label: "Year" },
    { key: "url", label: "URL", wide: true },
  ],
  website: [
    { key: "title", label: "Page title", wide: true },
    { key: "website", label: "Website name" },
    { key: "date", label: "Publication date", placeholder: DATE_HINT },
    { key: "url", label: "URL", wide: true },
    { key: "accessed", label: "Access date", placeholder: DATE_HINT },
  ],
};

const PEOPLE: Record<string, { key: "authors" | "editors"; label: string }[]> = {
  book: [
    { key: "authors", label: "Authors" },
    { key: "editors", label: "Editors" },
  ],
  chapter: [
    { key: "authors", label: "Chapter authors" },
    { key: "editors", label: "Book editors" },
  ],
  article: [{ key: "authors", label: "Authors" }],
  report: [{ key: "authors", label: "Authors or issuing body" }],
  thesis: [{ key: "authors", label: "Author" }],
  website: [{ key: "authors", label: "Authors" }],
};

function PeopleEditor({ label, people, onChange }: { label: string; people: Person[]; onChange: (people: Person[]) => void }) {
  const update = (index: number, person: Person) => onChange(people.map((p, i) => (i === index ? person : p)));
  return (
    <fieldset className="sm:col-span-2">
      <legend className="label">{label}</legend>
      <div className="space-y-2">
        {people.map((person, index) => {
          const organisation = person.literal !== undefined;
          return (
            <div key={index} className="flex flex-wrap items-center gap-2">
              {organisation ? (
                <input
                  className="input min-w-0 flex-1"
                  placeholder="Organisation name"
                  aria-label={`${label}: organisation name`}
                  value={person.literal || ""}
                  onChange={(e) => update(index, { literal: e.target.value })}
                />
              ) : (
                <>
                  <input
                    className="input min-w-0 flex-1"
                    placeholder="Given names"
                    aria-label={`${label}: given names`}
                    value={person.given || ""}
                    onChange={(e) => update(index, { ...person, given: e.target.value })}
                  />
                  <input
                    className="input min-w-0 flex-1"
                    placeholder="Surname"
                    aria-label={`${label}: surname`}
                    value={person.family || ""}
                    onChange={(e) => update(index, { ...person, family: e.target.value })}
                  />
                </>
              )}
              <label className="flex items-center gap-1 text-xs text-ink-soft">
                <input
                  type="checkbox"
                  checked={organisation}
                  onChange={(e) =>
                    update(
                      index,
                      e.target.checked
                        ? { literal: [person.given, person.family].filter(Boolean).join(" ") }
                        : { given: "", family: person.literal || "" },
                    )
                  }
                />
                Organisation
              </label>
              <button type="button" className="btn !px-2 !py-1 text-xs" aria-label={`Remove ${label} ${index + 1}`} onClick={() => onChange(people.filter((_, i) => i !== index))}>
                Remove
              </button>
            </div>
          );
        })}
        <button type="button" className="btn !py-1 text-xs" onClick={() => onChange([...people, { given: "", family: "" }])}>
          + Add name
        </button>
      </div>
    </fieldset>
  );
}

export default function MetadataForm({ metadata, onChange, flagged = {} }: { metadata: Metadata; onChange: (metadata: Metadata) => void; flagged?: Record<string, string> }) {
  const fields = FIELDS[metadata.type] || FIELDS.book;
  const set = (key: string, value: string | Person[]) => onChange({ ...metadata, [key]: value });

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <label className="label" htmlFor="source-type">
          Source type
        </label>
        <select id="source-type" className="input sm:!w-64" value={metadata.type} onChange={(e) => set("type", e.target.value)}>
          {Object.entries(TYPE_LABELS).map(([id, label]) => (
            <option key={id} value={id}>
              {label}
            </option>
          ))}
        </select>
      </div>
      {(PEOPLE[metadata.type] || []).map((group) => (
        <PeopleEditor key={group.key} label={group.label} people={(metadata[group.key] as Person[]) || []} onChange={(people) => set(group.key, people)} />
      ))}
      {fields.map((field) => (
        <div key={field.key} className={field.wide ? "sm:col-span-2" : ""}>
          <label className="label" htmlFor={`field-${field.key}`}>
            {field.label}
            {flagged[field.key] && <span className="ml-1.5 font-normal text-amber-700">· {flagged[field.key]}</span>}
          </label>
          <input
            id={`field-${field.key}`}
            className="input"
            placeholder={field.placeholder}
            value={(metadata[field.key] as string) || ""}
            onChange={(e) => set(field.key, e.target.value)}
          />
        </div>
      ))}
    </div>
  );
}
