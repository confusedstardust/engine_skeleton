CREATE TABLE IF NOT EXISTS site_daily_visitors (
    visit_date DATE NOT NULL,
    visitor_hash BINARY(32) NOT NULL,
    PRIMARY KEY (visit_date, visitor_hash)
) ENGINE=InnoDB;
