"""Principal component analysis (singular value decomposition): which combinations of the columns carry most of the
variation. Explained variance per component, loadings (how much each column weighs), scores of every row on the
components — plotted PC1 against PC2, coloured by a group column if given."""
import numpy as np
import pandas as pd

PLUGIN = {
    'id': 'pca',
    'order': 40,
    'name': {'en': 'Principal components (PCA)', 'it': 'Componenti principali (PCA)'},
    'category': 'stats',
    'description': {'en': 'Reduce many numeric columns to a few components: explained variance, loadings and the scores '
                          'plot (PC1 vs PC2), coloured by group.',
                    'it': 'Riduci molte colonne numeriche a poche componenti: varianza spiegata, loadings e il grafico '
                          'degli score (PC1 vs PC2), colorato per gruppo.'},
    'requires': [],
    'params': [
        {'id': 'columns', 'type': 'columns', 'default': 'ys', 'min_count': 2,
         'label': {'en': 'Numeric columns', 'it': 'Colonne numeriche'}},
        {'id': 'group', 'type': 'column', 'optional': True, 'default': 'hue',
         'label': {'en': 'Colour by (optional)', 'it': 'Colora per (facoltativa)'}},
        {'id': 'scale', 'type': 'bool', 'default': True,
         'label': {'en': 'Standardise the columns (different units)', 'it': 'Standardizza le colonne (unità diverse)'}},
        {'id': 'components', 'type': 'int', 'default': 3, 'min': 1, 'max': 50,
         'label': {'en': 'Components to report', 'it': 'Componenti da riportare'}},
    ],
    'references': [
        'Pearson, K. On lines and planes of closest fit to systems of points in space. Philos. Mag. 2, 559–572 (1901). '
        'doi:10.1080/14786440109462720',
        'Jolliffe, I. T. & Cadima, J. Principal component analysis: a review and recent developments. Phil. Trans. R. '
        'Soc. A 374, 20150202 (2016). doi:10.1098/rsta.2015.0202',
        'Harris, C. R. et al. Array programming with NumPy. Nature 585, 357–362 (2020). doi:10.1038/s41586-020-2649-2',
    ],
}


def run(df, p, ctx):
    cols = list(dict.fromkeys(p['columns']))
    block = pd.concat([ctx.numeric(df, c, dropna=False) for c in cols], axis=1)
    block.columns = cols
    keep = block.notna().all(axis=1)
    X = block[keep].to_numpy(float)
    if X.shape[0] < 3:
        raise ValueError(ctx.tr('At least three complete rows are needed.', 'Servono almeno tre righe complete.'))
    sd = X.std(axis=0, ddof=1)
    if np.any(sd == 0):
        raise ValueError(ctx.tr('A column is constant: leave it out.', 'Una colonna è costante: lasciala fuori.'))
    Z = (X - X.mean(axis=0)) / (sd if p['scale'] else 1.0)
    U, S, Vt = np.linalg.svd(Z, full_matrices=False)
    for i in range(Vt.shape[0]):                       # sign convention: the largest loading of each PC positive
        if Vt[i, np.argmax(np.abs(Vt[i]))] < 0:
            Vt[i] *= -1
            U[:, i] *= -1
    var = S ** 2 / (X.shape[0] - 1)
    ratio = var / var.sum()
    k = int(min(p['components'], len(S)))
    names = [f'PC{i + 1}' for i in range(len(S))]
    r = ctx.result()
    r.table(ctx.tr('Explained variance', 'Varianza spiegata'),
            pd.DataFrame({ctx.tr('component', 'componente'): names, ctx.tr('eigenvalue', 'autovalore'): var,
                          '%': 100 * ratio, ctx.tr('cumulative %', '% cumulata'): 100 * np.cumsum(ratio)}))
    loadings = pd.DataFrame(Vt[:k].T, index=cols, columns=names[:k])
    r.table(ctx.tr('Loadings (weight of each column)', 'Loadings (peso di ogni colonna)'), loadings.round(4), index=True)
    r.value(ctx.tr('rows used', 'righe usate'), int(X.shape[0]))
    r.value(ctx.tr('PC1 explains', 'PC1 spiega'), 100 * ratio[0], unit='%', key='pc1')
    if len(ratio) > 1:
        r.value(ctx.tr('PC1 + PC2 explain', 'PC1 + PC2 spiegano'), 100 * ratio[:2].sum(), unit='%', key='pc12')
    kaiser = int(np.sum(var > 1)) if p['scale'] else None
    if kaiser is not None:
        r.value(ctx.tr('components with eigenvalue > 1 (Kaiser)', 'componenti con autovalore > 1 (Kaiser)'), kaiser)
    top = loadings.iloc[:, 0].abs().sort_values(ascending=False).index[:3]
    r.text(ctx.tr(f'PC1 is driven mostly by: {", ".join(top)}.', f'PC1 è guidata soprattutto da: {", ".join(top)}.'))
    scores = pd.DataFrame(U[:, :max(2, k)] * S[:max(2, k)], columns=names[:max(2, k)]) if len(S) > 1 else \
        pd.DataFrame({'PC1': U[:, 0] * S[0]})
    plot = {'kind': 'scatter', 'x': 'PC1', 'y': ['PC2'] if 'PC2' in scores else ['PC1']}
    if p.get('group'):
        scores.insert(0, p['group'], df.loc[keep, p['group']].astype(str).to_numpy())
        plot['hue'] = p['group']
    plot['text'] = {'xlabel': f'PC1 ({100 * ratio[0]:.1f}%)',
                    'ylabel': f'PC2 ({100 * ratio[1]:.1f}%)' if len(ratio) > 1 else ''}
    r.data(scores, name=ctx.tr('PCA scores', 'score PCA'), plot=plot)
    return r
