from digest.dedup import _cosine_matrix, _semantic_clusters


def test_cosine_matrix_identical_vectors_score_one():
    m = _cosine_matrix([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
    assert round(m[0][1], 6) == 1.0           # identical direction
    assert round(m[0][2], 6) == 0.0           # orthogonal


def test_clusters_auto_merge_above_high():
    # 0 and 1 very similar (0.95), 2 unrelated. No gray band needed.
    sim = [[1.0, 0.95, 0.0],
           [0.95, 1.0, 0.1],
           [0.0, 0.1, 1.0]]
    clusters = _semantic_clusters(3, sim, sim_high=0.92, sim_low=0.82,
                                  gray_check=lambda pairs: set())
    assert sorted(map(sorted, clusters)) == [[0, 1], [2]]


def test_clusters_gray_band_consults_checker():
    # 0,1 in the gray band (0.85). Only merge if gray_check says yes.
    sim = [[1.0, 0.85], [0.85, 1.0]]
    merged = _semantic_clusters(2, sim, 0.92, 0.82,
                                gray_check=lambda pairs: set(pairs))
    assert sorted(map(sorted, merged)) == [[0, 1]]
    apart = _semantic_clusters(2, sim, 0.92, 0.82,
                               gray_check=lambda pairs: set())
    assert sorted(map(sorted, apart)) == [[0], [1]]
