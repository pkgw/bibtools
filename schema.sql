CREATE TABLE pubs (
       id INTEGER PRIMARY KEY,
       abstract TEXT,
       arxiv TEXT,
       bibcode TEXT,
       doi TEXT,
       firstsurname TEXT,
       title TEXT,
       year INTEGER
);

CREATE TABLE pdfs (
       sha1 TEXT PRIMARY KEY,
       pubid INTEGER
);
