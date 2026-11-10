export type Person = { given?: string; family?: string; literal?: string };

export type Metadata = {
  type: string;
  authors?: Person[];
  editors?: Person[];
  [key: string]: string | Person[] | undefined;
};

export type Pinpoint = { kind: string; value: string } | null;

export type CitationForm = { label: string; text: string; html: string };

export type Citations = {
  style: string;
  forms: Record<"full" | "footnote" | "short" | "bibliography", CitationForm>;
  missing: { required: string[]; recommended: string[] };
};

export type Source = { name: string; url: string; reliable: boolean; retrieved_at?: string };

export type Verification = {
  status: "verified" | "partially_verified" | "needs_review" | "user_confirmed";
  label: string;
  summary: string;
  checks: { field: string; label: string; state: "confirmed" | "edited" | "unverified" | "missing" }[];
  missing: { required: string[]; recommended: string[] };
  source: Source | null;
  disclaimer: string;
};

export type Candidate = {
  metadata: Metadata;
  source: Source;
  match: "identifier" | "exact_title" | "search";
  citations: Citations;
  verification: Verification;
};

export type IdentifyResult = {
  input_kind: "doi" | "isbn" | "url" | "text";
  query: string;
  candidates: Candidate[];
  warnings: string[];
  message: string;
};

export type Reference = {
  id: number;
  type: string;
  metadata: Metadata;
  retrieved: Metadata | null;
  source: Source | null;
  pinpoint: Pinpoint;
  style: string;
  notes: string;
  tags: string[];
  favorite: boolean;
  user_confirmed: boolean;
  collection_ids: number[];
  created_at: string;
  updated_at: string;
  citations: Citations;
  verification: Verification;
};

export type Collection = { id: number; name: string; description: string; kind: "research" | "moot"; count: number };

export type User = { id: number; email: string; default_style: string; default_export_format: string };

export type Duplicate = { id: number; reasons: string[]; title: string; type: string; citation: CitationForm };

export type Section = { heading: string; entries: { id: number | null; text: string; html: string }[] };

export type Category = { heading: string; types: string[] };

export type Stats = {
  total: number;
  legal: number;
  academic: number;
  by_type: Record<string, number>;
  verification: Record<string, number>;
  collections: number;
  recent: Reference[];
  favorites: Reference[];
};

export const STYLES = [
  { id: "oscola", name: "OSCOLA" },
  { id: "bluebook", name: "Bluebook" },
  { id: "apa", name: "APA 7th" },
];

export const TYPE_LABELS: Record<string, string> = {
  case: "Case",
  legislation: "Legislation",
  treaty: "Treaty",
  book: "Book",
  chapter: "Book chapter",
  article: "Journal article",
  report: "Report or paper",
  thesis: "Thesis",
  website: "Website",
};

export const TYPE_PLURALS: Record<string, string> = {
  case: "Cases",
  legislation: "Legislation",
  treaty: "Treaties",
  book: "Books",
  chapter: "Book chapters",
  article: "Journal articles",
  report: "Reports",
  thesis: "Theses",
  website: "Websites",
};

export const EXPORT_FORMATS = [
  { id: "docx", name: "Word (DOCX)" },
  { id: "pdf", name: "PDF" },
  { id: "txt", name: "Plain text (TXT)" },
  { id: "bibtex", name: "BibTeX" },
  { id: "ris", name: "RIS" },
  { id: "csv", name: "CSV" },
  { id: "csl-json", name: "CSL-JSON" },
];
