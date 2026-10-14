"""Cluster analysis: groups of rows that resemble each other across numeric columns. k-means (best of several starts)
or hierarchical clustering (Ward); the number of clusters given, or chosen by the mean silhouette. Reports the size and
centre of each cluster and the silhouette; the rows with their cluster can be plotted and exported."""
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'clustering',
    'order': 41,
    'name': {'en': 'Cluster analysis (k-means, Ward)', 'it': 'Analisi dei cluster (k-means, Ward)'},
    'category': 'stats',
    'description': {'en': 'Find groups of similar rows: k-means or hierarchical (Ward), the number of clusters given or '
                          'chosen by the silhouette.',
                    'it': 'Trova gruppi di righe simili: k-means o gerarchico (Ward), con il numero di cluster dato o '
                          'scelto dalla silhouette.'},
    'suits': [                                          # figures it suits (piplotter/advisor.py)
        {'figure': 'columns', 'score': 64,
         'reason': {'en': 'Groups of rows that resemble each other (k-means, Ward).',
                    'it': 'Gruppi di righe che si somigliano (k-means, Ward).'}},
    ],
    'requires': ['scipy'],
    'params': [
        {'id': 'columns', 'type': 'columns', 'default': 'ys', 'min_count': 1,
         'label': {'en': 'Numeric columns', 'it': 'Colonne numeriche'}},
        {'id': 'method', 'type': 'choice', 'default': 'kmeans', 'label': {'en': 'Method', 'it': 'Metodo'},
         'choices': [{'value': 'kmeans', 'label': 'k-means'},
                     {'value': 'ward', 'label': {'en': 'hierarchical (Ward)', 'it': 'gerarchico (Ward)'}}]},
        {'id': 'k', 'type': 'int', 'optional': True, 'min': 2, 'max': 30,
         'label': {'en': 'Number of clusters (empty = best silhouette, 2–8)', 'it': 'Numero di cluster (vuoto = miglior silhouette, 2–8)'}},
        {'id': 'scale', 'type': 'bool', 'default': True,
         'label': {'en': 'Standardise the columns (different units)', 'it': 'Standardizza le colonne (unità diverse)'}},
    ],
    'references': [
        'MacQueen, J. Some methods for classification and analysis of multivariate observations. Proc. 5th Berkeley '
        'Symp. Math. Stat. Prob. 1, 281–297 (1967).',
        'Ward, J. H. Hierarchical grouping to optimize an objective function. J. Am. Stat. Assoc. 58, 236–244 (1963). '
        'doi:10.1080/01621459.1963.10500845',
        'Rousseeuw, P. J. Silhouettes: a graphical aid to the interpretation and validation of cluster analysis. '
        'J. Comput. Appl. Math. 20, 53–65 (1987). doi:10.1016/0377-0427(87)90125-7',
        'Virtanen, P. et al. SciPy 1.0. Nature Methods 17, 261–272 (2020). doi:10.1038/s41592-019-0686-2',
    ],
}

MAX_SILHOUETTE = 3000          # rows used for the silhouette (a random sample above this)


def kmeans(Z, k, starts=10):
    from scipy.cluster.vq import kmeans2
    best, best_inertia = None, np.inf
    for seed in range(starts):
        centres, labels = kmeans2(Z, k, minit='++', seed=seed)
        inertia = float(np.sum((Z - centres[labels]) ** 2))
        if inertia < best_inertia and len(np.unique(labels)) == k:
            best, best_inertia = labels, inertia
    if best is None:
        raise ValueError('k-means did not find that many separate clusters.')
    return best


def ward(Z, k):
    from scipy.cluster.hierarchy import fcluster, linkage
    return fcluster(linkage(Z, method='ward'), k, criterion='maxclust') - 1


def silhouette(Z, labels):
    """Mean silhouette (Rousseeuw): (b − a) / max(a, b) per point, a the mean distance within its cluster, b to the
    nearest other cluster."""
    from scipy.spatial.distance import cdist
    if Z.shape[0] > MAX_SILHOUETTE:
        pick = np.random.default_rng(0).choice(Z.shape[0], MAX_SILHOUETTE, replace=False)
        Z, labels = Z[pick], labels[pick]
    D = cdist(Z, Z)
    ks = np.unique(labels)
    s = np.zeros(Z.shape[0])
    for i in range(Z.shape[0]):
        own = labels == labels[i]
        if own.sum() <= 1:
            continue
        a = D[i, own].sum() / (own.sum() - 1)
        b = min(D[i, labels == c].mean() for c in ks if c != labels[i])
        s[i] = (b - a) / max(a, b) if max(a, b) > 0 else 0.0
    return float(s.mean())


def run(df, p, ctx):
    cols = list(dict.fromkeys(p['columns']))
    block = pd.concat([ctx.numeric(df, c, dropna=False) for c in cols], axis=1)
    block.columns = cols
    keep = block.notna().all(axis=1)
    X = block[keep].to_numpy(float)
    if X.shape[0] < 6:
        raise ValueError(ctx.tr('At least six complete rows are needed.', 'Servono almeno sei righe complete.'))
    sd = X.std(axis=0, ddof=1)
    Z = (X - X.mean(axis=0)) / np.where(sd > 0, sd, 1.0) if p['scale'] else X - X.mean(axis=0)
    cluster = kmeans if p['method'] == 'kmeans' else ward
    r = ctx.result()
    if p.get('k'):
        k = int(p['k'])
        if k >= X.shape[0]:
            raise ValueError(ctx.tr('More clusters than rows.', 'Più cluster che righe.'))
        labels = cluster(Z, k)
        sil = silhouette(Z, labels)
    else:
        tried = []
        for k in range(2, min(8, X.shape[0] - 1) + 1):
            try:
                lab = cluster(Z, k)
            except ValueError:
                continue
            tried.append((silhouette(Z, lab), k, lab))
        if not tried:
            raise ValueError(ctx.tr('No clustering found.', 'Nessun raggruppamento trovato.'))
        sil, k, labels = max(tried, key=lambda t: t[0])
        r.table(ctx.tr('Number of clusters by silhouette', 'Numero di cluster per silhouette'),
                pd.DataFrame({'k': [t[1] for t in tried], 'silhouette': [t[0] for t in tried]}))
    # Clusters numbered by size, largest first.
    order = {c: i + 1 for i, c in enumerate(pd.Series(labels).value_counts().index)}
    labels = np.array([order[c] for c in labels])
    name = ctx.tr('cluster', 'cluster')
    centres = pd.DataFrame(X).groupby(labels).mean()
    centres.columns = cols
    centres.insert(0, 'N', pd.Series(labels).value_counts().sort_index().to_numpy())
    centres.index = [f'{name} {i}' for i in centres.index]
    r.table(ctx.tr('Clusters: size and centre (original units)', 'Cluster: numerosità e centro (unità originali)'),
            centres.round(4), index=True)
    r.value(ctx.tr('clusters', 'cluster'), int(k), key='k')
    r.value(ctx.tr('mean silhouette (1 = well separated, ≤ 0.25 = weak)', 'silhouette media (1 = ben separati, ≤ 0,25 = debole)'),
            sil, key='silhouette')
    out = block[keep].reset_index(drop=True)
    out.insert(0, name, [f'{name} {c}' for c in labels])
    plot = {'kind': 'scatter', 'x': cols[0], 'y': [cols[1] if len(cols) > 1 else cols[0]], 'hue': name}
    r.data(out, name=ctx.tr('rows with their cluster', 'righe con il loro cluster'), plot=plot)
    return r
