CREATE TABLE pubs (
       id INTEGER UNIQUE PRIMARY KEY,
       abstract TEXT,
       arxiv TEXT,
       bibcode TEXT,
       doi TEXT,
       keep INTEGER,
       nfas TEXT, /* normalized first-author surname */
       refdata TEXT, /* JSON dict */
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

CREATE TABLE history (
       date INTEGER PRIMARY KEY,
       pubid INTEGER,
       action INTEGER
);

CREATE TABLE nicknames (
       nickname TEXT UNIQUE PRIMARY KEY,
       pubid INTEGER
);

CREATE TABLE notes (
       pubid INTEGER,
       note TEXT
);

CREATE TABLE pdfs (
       sha1 TEXT UNIQUE PRIMARY KEY,
       pubid INTEGER
);

CREATE TABLE publists (
       type INTEGER,
       idx INTEGER,
       pubid INTEGER
);
