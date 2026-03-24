from core.search import SearchResult, _clipboard
from core.calc_eval import calc_eval, calc_match_query, normalize_expression


class CalcRunner:
    def match(self, query: str) -> list[SearchResult]:
        expr, _ = calc_match_query(query)
        if not expr:
            return []
        expr = normalize_expression(expr)
        disp, err = calc_eval(expr)
        uk = f"calc:{expr}"
        if disp is None:
            if err:
                return [SearchResult(
                    title="= Ошибка",
                    subtitle=err,
                    icon_name="dialog-warning",
                    score=0.85,
                    category="Калькулятор",
                    preview_kind="calc",
                    preview_text=expr,
                    usage_key=uk,
                    action=lambda: None,
                )]
            return []
        return [SearchResult(
            title="= " + disp,
            subtitle=expr + " · Enter — скопировать",
            icon_name="accessories-calculator",
            score=1.0,
            category="Калькулятор",
            preview_kind="calc",
            preview_text=expr,
            usage_key=uk,
            action=lambda r=disp: _clipboard(r),
        )]


RUNNERS = [CalcRunner()]
