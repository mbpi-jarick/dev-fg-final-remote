# app_helpers.py

def find_best_match_column(columns, keywords, priority_exact=None):
    """
    Finds the best matching column from a list of columns based on a prioritized search.

    Args:
        columns (list): A list of column names to search through.
        keywords (list): A list of keywords to look for (e.g., ['code', 'product']).
        priority_exact (list, optional): A list of exact column names to prioritize.
    """
    columns_lower = {c.lower(): c for c in columns}

    # 1. Highest Priority: Exact matches (case-insensitive)
    if priority_exact:
        for p_exact in priority_exact:
            if p_exact.lower() in columns_lower:
                return columns_lower[p_exact.lower()]

    # 2. Second Priority: Starts with a keyword
    for kw in keywords:
        for col_lower, col_original in columns_lower.items():
            if col_lower.startswith(kw):
                return col_original

    # 3. Third Priority: Contains a keyword
    for kw in keywords:
        for col_lower, col_original in columns_lower.items():
            if kw in col_lower:
                return col_original

    return None