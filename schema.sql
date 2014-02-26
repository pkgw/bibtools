CREATE TABLE pubs (
       id INTEGER UNIQUE PRIMARY KEY,
       abstract TEXT,
       arxiv TEXT,
       bibcode TEXT,
       doi TEXT,
       firstsurname TEXT,
       title TEXT,
       year INTEGER
);

CREATE TABLE author_names (
       name TEXT UNIQUE PRIMARY KEY
);

CREATE TABLE authors (
       pubid INTEGER,
       idx INTEGER,
       authid INTEGER
);

CREATE TABLE nicknames (
       nickname TEXT UNIQUE PRIMARY KEY,
       pubid INTEGER
);

CREATE TABLE pdfs (
       sha1 TEXT UNIQUE PRIMARY KEY,
       pubid INTEGER
);
