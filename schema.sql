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
       name TEXT UNIQUE PRIMARY KEY NOT NULL
);

CREATE TABLE authors (
       type INTEGER NOT NULL,
       pubid INTEGER NOT NULL,
       idx INTEGER NOT NULL,
       authid INTEGER NOT NULL,
       FOREIGN KEY (pubid) REFERENCES pubs(id),
       FOREIGN KEY (authid) REFERENCES author_names(oid)
);

CREATE TABLE history (
       date INTEGER PRIMARY KEY NOT NULL,
       pubid INTEGER NOT NULL,
       action INTEGER NOT NULL,
       FOREIGN KEY (pubid) REFERENCES pubs(id)
);

CREATE TABLE nicknames (
       nickname TEXT UNIQUE PRIMARY KEY NOT NULL,
       pubid INTEGER NOT NULL,
       FOREIGN KEY (pubid) REFERENCES pubs(id)
);

CREATE TABLE notes (
       pubid INTEGER NOT NULL,
       note TEXT NOT NULL,
       FOREIGN KEY (pubid) REFERENCES pubs(id)
);

CREATE TABLE pdfs (
       sha1 TEXT UNIQUE PRIMARY KEY NOT NULL,
       pubid INTEGER NOT NULL,
       FOREIGN KEY (pubid) REFERENCES pubs(id)
);

CREATE TABLE publists (
       name TEXT NOT NULL,
       idx INTEGER NOT NULL,
       pubid INTEGER NOT NULL,
       FOREIGN KEY (pubid) REFERENCES pubs(id),
       UNIQUE (name, pubid)
);
