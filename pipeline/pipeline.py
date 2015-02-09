"""
This module provides a data processing pipeline for the DBLP dataset.
The results include a paper co-citation graph, an author co-citation
graph, and several useful node attributes, including venues for both
papers and authors and term frequencies for author documents.
"""

import os, sys, csv
import pandas as pd
import igraph, gensim
import doctovec

# INPUT FILES
ORIG_PAPER_FILE = 'paper-with-venue-and-year-no-single-venues.csv'
PAPER_FILE = 'paper.csv'
AUTHOR_FILE = 'author.csv'
PERSON_FILE = 'person.csv'
REFS_FILE = 'refs.csv'

# OUTPUT FILES
VENUE_FILE = 'venue.csv'
YEAR_FILE = 'year.csv'


def write_csv(fname, header, rows):
    """Write an iterable of records to a csv file with optional header."""
    with open('%s.csv' % fname, 'w') as f:
        writer = csv.writer(f)
        if header: writer.writerow(header)
        writer.writerows(rows)

def yield_csv_records(csv_file):
    with open(csv_file) as f:
        reader = csv.reader(f)
        reader.next()
        for record in reader:
            yield record

# ---------------------------------------------------------
# remove venues that only occur once
# ---------------------------------------------------------

import pandas as pd

infile = 'paper-with-venue-and-year.csv'
outfile = 'paper-with-venue-and-year-no-single-venue.csv'
def remove_single_venues(paper_file, outfile):
    df = pd.read_csv(paper_file))
    multiple = df.groupby('venue')['venue'].transform(len) > 1
    filtered = df[multiple]
    filtered.to_csv(outfile, index=False)

remove_single_venues(infile, outfile)

# ---------------------------------------------------------
# filter data to a range of years
# ---------------------------------------------------------

start = 1994
end = 2004

def filter_by_year_range(start, end):
    # filter the papers by year
    df = pd.read_csv(ORIG_PAPER_FILE)
    df['year'] = df['year'].astype(int)
    df = df[(df['year'] >= start) & (df['year'] <= end)]

    # load authors and refs for later filtering
    author_df = pd.read_csv(AUTHOR_FILE)
    person_df = pd.read_csv(PERSON_FILE)
    refs_df = pd.read_csv(REFS_FILE)

    # change to new dir to prepare to write new set of files
    newdir = '%d-to-%d' % (start, end)
    init_wd = os.getcwd()
    try: os.mkdir(newdir)
    except OSError: pass
    os.chdir(newdir)

    # write new paper.csv file
    df.to_csv(PAPER_FILE, index=False)

    # write new venue listing
    rows = sorted([(venue,) for venue in df['venue'].unique()])
    write_csv(VENUE_FILE, None, rows)

    # write new year listing
    rows = sorted([(year,) for year in df['year'].unique()])
    write_csv(YEAR_FILE, None, rows)

    # filter authors and refs to only those in the filtered time range
    paper_ids = df['id'].unique()
    author_df = author_df[author_df['paper_id'].isin(paper_ids)]
    author_ids = author_df['author_id'].unique()
    person_df = person_df[person_df['id'].isin(author_ids)]
    refs_df = refs_df[(refs_df['paper_id'].isin(paper_ids)) &
                      (refs_df['ref_id'].isin(paper_ids))]

    # now write the filtered records
    author_df.to_csv(AUTHOR_FILE, index=False)
    person_df.to_csv(PERSON_FILE, index=False)
    refs_df.to_csv(REFS_FILE, index=False)

    # All done; restore previous working directory
    os.chdir(init_wd)

# Now actually do the filtering
filter_by_year_range(start, end)


# ---------------------------------------------------------
# build repdocs for each paper
# ---------------------------------------------------------

import csv
import gensim
import doctovec

def read_repdocs(papers_file):
    with open(papers_file) as f:
        reader = csv.reader(f)
        reader.next()
        records = ((r[0], '%s %s' % (r[1], r[4])) for r in reader)
        for doid, doc in records:
            yield (docid, doc.decode('utf-8'))

def write_paper_repdocs(docs, outfile='repdoc-by-paper.csv'):
    with open(outfile, 'w') as doc_file:
        doc_writer = csv.writer(doc_file)
        doc_writer.writerow(('paper_id', 'doc'))
        for docid, doc in docs:
            doc_writer.writerow((docid, doc.encode('utf-8')))
            yield (docid, doc)

def write_paper_repdoc_vectors(docs, outfile='repdoc-by-paper-vectors.csv')
    with open(outfile, 'w') as vec_file:
        vec_writer = csv.writer(vec_file)
        vec_writer.writerow(('paper_id', 'doc'))
        for docid, doc in docs:
            vector = doctovec.doctovec(doc)
            concat = '|'.join(vector).encode('utf-8')
            vec_writer.writerow((docid, concat))
            yield (docid, doc)

# Set up the pipeline.
repdocs = write_paper_repdoc_vectors(
            write_paper_repdocs(
                read_repdocs(PAPER_FILE)))

dictionary = gensim.corpora.Dictionary(repdocs)
print 'term count in paper repdoc corpus pre-filtering: %d' % len(dictionary)
dictionary.filter_extremes(2, 1, len(dictionary))
print 'term count in paper repdoc corpus post-filtering: %d' % len(dictionary)
dictionary.save('paper-repdoc-corpus.dict')


# ---------------------------------------------------------
# parse repdocs into author vectors
# ---------------------------------------------------------

import csv, pandas as pd


def build_author_repdocs(paper_repdocs_file='repdoc-by-paper-vectors.csv',
                         author_repdocs_file='repdoc-by-author-vectors.csv'):
    # big memory demand
    df = pd.read_csv(paper_repdocs_file, index_col=(0,))
    df.fillna('', inplace=True)

    # read out authorship records
    author_df = pd.read_csv(AUTHOR_FILE, header=0, index_col=(0,))

    # initialize repdoc dictionary from complete list of person ids
    author_ids = author_df.index.unique()
    repdocs = {i: [] for i in author_ids}

    # build up repdocs for each author
    for person_id, paper_id in author_df.itertuples():
        doc = df.loc[paper_id]['doc']
        repdocs[person_id].append(doc)

    # save repdocs
    rows = ((person_id, '|'.join(docs))
            for person_id, docs in repdocs.iteritems())
    write_csv(author_repdocs_file, ('author_id', 'doc'), rows)

build_author_repdocs()

# -----------------------------------------------------------
# build paper citation graph using paper.csv
# -----------------------------------------------------------

import igraph, csv

def read_paper_vertices(paper_file):
    """Iterate through paper IDs from the paper csv file."""
    with open(PAPER_FILE) as f:
        reader = csv.reader(f)
        reader.next()
        for row in reader:
            yield row[0]

def read_paper_venues(paper_file):
    """Iterate through (paper_id, venue) pairs from the paper csv file."""
    reader = csv.reader(f)
    reader.next()
    for row in reader:
        yield (row[0], row[2])

def read_paper_references(refs_file, idmap):
    """Filter out references to papers outside dataset."""
    for paper_id, ref_id in yield_csv_records(refs_file):
        try: yield (idmap[paper_id], idmap[ref_id])
        except: pass

def build_paper_citation_graph(paper_file, author_file, refs_file,
                               idmap_fname='paper-id-to-node-id-map',
                               save=True, out_fname='paper-citation-graph'):
    # get paper ids from csv file and add to graph
    refg = igraph.Graph()
    nodes = read_paper_vertices(PAPER_FILE)
    refg.add_vertices(nodes)

    # paper id to node id mapping; make and save
    idmap = {v['name']: v.index for v in refg.vs}
    rows = idmap.iteritems()
    write_csv(idmap_fname, ('paper_id', 'node_id'), rows)

    # now add venues to vertices as paper attributes
    paper_venues = read_paper_venues(PAPER_FILE)
    for paper_id, venue in paper_venues:
        node_id = idmap[paper_id]
        refg.vs[node_id]['venue'] = venue

    # next add author ids
    for v in refg.vs:
        v['author_ids'] = []

    author_records = yield_csv_records(author_file)
    for author_id, paper_id in reader:
        node_id = idmap[paper_id]
        refg.vs[node_id]['author_ids'].append(author_id)

    # Finally add edges from citation records
    citation_links = read_paper_references(refs_file, idmap)
    refg.add_edges(citation_links)

    # Save if requested
    if save:
        refg.write_picklez('%s.pickle.gz' % out_fname)
        refg.write_graphmlz('%s.graphml.gz' % out_fname)

    return refg

# Build and save the graph
build_paper_citation_graph(PAPER_FILE, AUTHOR_FILE, REFS_FILE)

# -----------------------------------------------------------
# build author citation graph using paper citation graph
# -----------------------------------------------------------

# reload idmap and paper citation graph
# -----------------------------------------------------------------------------
# fname = 'paper-id-to-node-id-map.csv'
# mapfile = open(fname)
# mapreader = csv.reader(mapfile)
# mapreader.next()
# idmap = {r[0]: int(r[1]) for r in mapreader}
# 
# refg = igraph.Graph.Read_Picklez('paper-citation-graph.pickle.gz')
# assert(len(idmap) == len(refg.vs))
# -----------------------------------------------------------------------------
# start here if continuing from above

import pandas as pd

# get person IDs
df = pd.read_csv(PERSON_FILE, header=0, usecols=(0,))
author_ids = df['id'].values

# get author records to build edges from
def get_paper_edges(paper_id, author_id):
    """Return a list of author-to-author edges for each paper."""
    node = refg.vs[paper_id]
    neighbors = node.neighbors()
    author_lists = [n['author_ids'] for n in neighbors]
    if not author_lists: return []
    authors = reduce(lambda x,y: x+y, author_lists)
    return zip([author_id]*len(authors), authors)

def get_edges(rows):
    """Return all edges from the list of (author, paper) rows."""
    while True:
        edges = get_paper_edges(*rows.next())
        for edge in edges:
            yield edge

# build the author citation graph and save it
def build_undirected_graph(nodes, edges):
    graph = igraph.Graph()
    graph.add_vertices(nodes)
    graph.add_edges(edges)
    graph.simplify()
    return graph

with open(AUTHOR_FILE) as f:
    reader = csv.reader(f)
    reader.next()
    rows = ((idmap[paper_id], author_id) for author_id, paper_id in reader)
    edges = get_edges(rows)
    nodes = (str(author_id) for author_id in author_ids)
    authorg = build_undirected_graph(nodes, edges)

authorg.write_graphmlz('author-citation-graph.graphml.gz')

def save_id_map(graph, outfile, idname='author'):
    """Save vertex ID to vertex name mapping and then return it."""
    first_col = '%s_id' % idname
    idmap = {v['name']: v.index for v in graph.vs}
    rows = sorted(idmap.items())
    with open('%s.csv' % outfile, 'w') as f:
        writer = csv.writer(f)
        writer.writerow((first_col, 'node_id'))
        writer.writerows(rows)
    return idmap

# save author id to node id map
author_idmap = save_id_map(authorg, 'author-id-to-node-id-map')

# extract the largest strongly connected component (LCC)
components = authorg.components()
lcc = components.giant()

# save the LCC and its id mapping
lcc.write_graphmlz('lcc-author-citation-graph.graphml.gz')
lcc.write_edgelist('lcc-author-citation-graph-edgelist.txt')
lcc_idmap = save_id_map(lcc, 'lcc-author-id-to-node-id-map')


# -----------------------------------------------------------
# build up ground-truth communities using venue info for LCC
# -----------------------------------------------------------

import igraph, pandas as pd

# load author, paper, venue info
author_df = pd.read_table(
        AUTHOR_FILE, sep=",", header=0,
        usecols=('author_id', 'paper_id'))
paper_df = pd.read_table(
        PAPER_FILE, sep=",", header=0,
        usecols=('id', 'venue'))
paper_df.columns = ('paper_id', 'venue')

# filter authors down to those in LCC
lcc_author_ids = set([int(v['name']) for v in lcc.vs])
selection = author_df['author_id'].isin(lcc_author_ids)
author_df = author_df[selection]
merge_df = author_df.merge(paper_df)
del merge_df['paper_id']

# assign each venue an id and save the assignment
unique_venues = merge_df['venue'].unique()
unique_venues.sort()
venue_map = {venue: vnum for vnum, venue in enumerate(unique_venues)}
rows = ((vnum, venue) for venue, vnum in venue_map.iteritems())
with open('lcc-venue-id-map.csv', 'w') as wf:
    venue_writer = csv.writer(wf)
    venue_writer.writerow(('venue_id', 'venue_name'))
    venue_writer.writerows(rows)

# add venue information to LCC
for v in lcc.vs:
    v['venues'] = set()

for rownum, row in merge_df.iterrows():
    author_id, venue = row
    node_id = lcc_idmap[str(author_id)]
    venue_id = venue_map[venue]
    lcc.vs[node_id]['venues'].add(venue_id)

for v in lcc.vs:
    v['venues'] = tuple(v['venues'])

# save a copy of the graph with venue info
lcc.write_picklez('lcc-author-citation-graph.pickle.gz')

# build ground truth communities
communities = {venue_id: [] for venue_id in venue_map.itervalues()}
for v in lcc.vs:
    for venue_id in v['venues']:
        communities[venue_id].append(v.index)

# save ground truth communities
fname = 'lcc-ground-truth-by-venue.txt'
comms = sorted(communities.items())
rows = (' '.join(map(str, comm)) for comm_num, comm in comms)
with open(fname, 'w') as f:
    f.write('\n'.join(rows))

# save venue info for each author separately
fname = 'lcc-author-venues.txt'
records = sorted([(v.index, v['venues']) for v in lcc.vs])
rows = (' '.join(map(str, venues)) for node_id, venues in records)
with open(fname, 'w') as f:
    f.write('\n'.join(rows))

# ---------------------------------------------------------
# convert author repdocs to tf/tfidf corpuses
# ---------------------------------------------------------

import gensim, sys, csv, igraph, pandas as pd

# filter authors down to those in LCC
df = pd.read_csv('lcc-author-id-to-node-id-map.csv', header=0, usecols=(0,))
lcc_author_ids = df['author_id'].values

# build dictionary of terms from repdocs
csv.field_size_limit(sys.maxint)
with open('repdoc-by-author-vectors.csv') as f:
    reader = csv.reader(f)
    reader.next()
    corpus = (doc.split('|') for author_id, doc in reader
              if int(author_id) in lcc_author_ids)
    dictionary = gensim.corpora.Dictionary(corpus)

# save dictionary and term id mapping
dictionary.save('lcc-repdoc-corpus.dict')
rows = [(term_id, term.encode('utf-8'))
        for term, term_id in dictionary.token2id.iteritems()]
rows = sorted(rows)  # put ids in order
with open('lcc-repdoc-corpus-term-id-map.csv', 'w') as f:
    writer = csv.writer(f)
    writer.writerow(('term_id', 'term'))
    writer.writerows(rows)

# write term frequency corpus
fname = 'lcc-repdoc-corpus-tf.mm'
with open('repdoc-by-author-vectors.csv') as f:
    reader = csv.reader(f)
    reader.next()
    corpus = (doc.split('|') for author_id, doc in reader
              if int(author_id) in lcc_author_ids)
    bow_corpus = (dictionary.doc2bow(doc) for doc in corpus)
    gensim.corpora.MmCorpus.serialize(fname, bow_corpus)

# write tfidf corpus
bow_corpus = gensim.corpora.MmCorpus(fname)
tfidf = gensim.models.TfidfModel(bow_corpus)
tfidf_corpus = tfidf[bow_corpus]
fname = 'lcc-repdoc-corpus-tfidf.mm'
gensim.corpora.MmCorpus.serialize(fname, tfidf_corpus)

# -----------------------------------------------------------------------------
# produce CESNA/CODA/EDCAR formatted data files
# -----------------------------------------------------------------------------

def swap_file_delim(infile, indelim, outfile, outdelim):
    with open(infile) as rf:
        in_lines = (l.strip().split(indelim) for l in rf)
        out_lines = (outdelim.join(l) for l in in_lines)
        with open(outfile, 'w') as wf:
            wf.write('\n'.join(out_lines))

# CODA requires only a tsv edgelist
swap_file_delim(
    'lcc-author-citation-graph-edgelist.txt', ' ',
    'lcc-author-citation-graph-edgelist.tsv', '\t')

# CESNA requires the same edgelist as CODA, but also requires
# (1) (node_id \t term_id) pairs for all term features
swap_file_delim(
    'lcc-repdoc-corpus-term-id-map.csv', ',',
    'lcc-repdoc-corpus-term-id-map.tsv', '\t')

# (2) (term_id \t term) pairs for all terms in the corpus
# note that because this is mm format, we need to subtract 1 from all ids
corpus = gensim.corpora.MmCorpus('lcc-repdoc-corpus-tf.mm')
with open('lcc-repdoc-corpus-author-term-presence.tsv', 'w') as wf:
    docs_with_tf = (
        docnum, corpus.docbyoffset(offset)
        for docnum, offset in enumerate(corpus.index))
    docs_as_pairs = (
        zip([docnum] * len(doc), [term_id for term_id, _ in doc])
        for docnum, doc in docs_with_tf)
    docs_as_lines = (
        ['%s\t%s' % (docid, termid) for docid, termid in pairs]
        for pairs in docs_as_pairs)
    docs = ('\n'.join(lines) for lines in docs_as_lines)

    for doc in docs:
        wf.write('\n'.join(doc))