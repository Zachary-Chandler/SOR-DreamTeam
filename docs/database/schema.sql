--
-- PostgreSQL database dump
--

\restrict vGoRKqiqpkXBgcpeBElh5KYBsgiGO0u7F1sIA7s2ThnQG9NwCzUouSbtrzx2wkd

-- Dumped from database version 18.6
-- Dumped by pg_dump version 18.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: cleaned; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA cleaned;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: address; Type: TABLE; Schema: cleaned; Owner: -
--

CREATE TABLE cleaned.address (
    addressid text NOT NULL,
    ind_idn text,
    snu_nbr text,
    sna_txt text,
    sud_cod text,
    sud_nbr text,
    cty_txt text,
    plc_cod text,
    zip_txt text,
    cou_cod text,
    lat_nbr text,
    lon_nbr text
);


--
-- Name: individual; Type: TABLE; Schema: cleaned; Owner: -
--

CREATE TABLE cleaned.individual (
    ind_idn text NOT NULL,
    dps_nbr text
);


--
-- Name: name; Type: TABLE; Schema: cleaned; Owner: -
--

CREATE TABLE cleaned.name (
    nam_idn text NOT NULL,
    per_idn text,
    typ_cod text,
    nam_txt text,
    lna_txt text,
    fna_txt text
);


--
-- Name: person; Type: TABLE; Schema: cleaned; Owner: -
--

CREATE TABLE cleaned.person (
    ind_idn text,
    per_idn text NOT NULL,
    sex_cod text,
    rac_cod text,
    hgt_qty text,
    wgt_qty text,
    hai_cod text,
    eye_cod text,
    eth_cod text
);


--
-- Name: individual_search; Type: VIEW; Schema: cleaned; Owner: -
--

CREATE VIEW cleaned.individual_search AS
 SELECT i.ind_idn,
    i.dps_nbr,
    p.per_idn,
    n.nam_idn,
    n.nam_txt,
    n.fna_txt,
    n.lna_txt,
    p.sex_cod,
    p.rac_cod,
    p.hgt_qty,
    p.wgt_qty
   FROM ((cleaned.individual i
     LEFT JOIN cleaned.person p ON ((i.ind_idn = p.ind_idn)))
     LEFT JOIN cleaned.name n ON ((p.per_idn = n.per_idn)));


--
-- Name: offense; Type: TABLE; Schema: cleaned; Owner: -
--

CREATE TABLE cleaned.offense (
    ind_idn text,
    offenseid text,
    coo_cod text,
    coj_cod text,
    joo_cod text,
    off_cod text,
    ver_nbr text,
    goc_cod text,
    dis_flg text,
    ost_cod text,
    cpr_cod text,
    cdd_dte timestamp without time zone,
    aov_nbr text,
    sov_cod text,
    cpr_val text,
    offense_record_id bigint NOT NULL
);


--
-- Name: offense_offense_record_id_seq; Type: SEQUENCE; Schema: cleaned; Owner: -
--

ALTER TABLE cleaned.offense ALTER COLUMN offense_record_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME cleaned.offense_offense_record_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: offense_summary; Type: VIEW; Schema: cleaned; Owner: -
--

CREATE VIEW cleaned.offense_summary AS
 SELECT ind_idn,
    count(*) AS total_offense_records,
    count(DISTINCT offenseid) AS unique_offenses,
    min(cdd_dte) AS earliest_offense_date,
    max(cdd_dte) AS latest_offense_date
   FROM cleaned.offense
  GROUP BY ind_idn;


--
-- Name: search_results; Type: VIEW; Schema: cleaned; Owner: -
--

CREATE VIEW cleaned.search_results AS
 SELECT s.ind_idn,
    s.dps_nbr,
    s.per_idn,
    s.nam_idn,
    s.nam_txt,
    s.fna_txt,
    s.lna_txt,
    s.sex_cod,
    s.rac_cod,
    s.hgt_qty,
    s.wgt_qty,
    COALESCE(o.total_offense_records, (0)::bigint) AS total_offense_records,
    COALESCE(o.unique_offenses, (0)::bigint) AS unique_offenses,
    o.earliest_offense_date,
    o.latest_offense_date
   FROM (cleaned.individual_search s
     LEFT JOIN cleaned.offense_summary o ON ((s.ind_idn = o.ind_idn)));


--
-- Name: address address_pk; Type: CONSTRAINT; Schema: cleaned; Owner: -
--

ALTER TABLE ONLY cleaned.address
    ADD CONSTRAINT address_pk PRIMARY KEY (addressid);


--
-- Name: individual individual_pk; Type: CONSTRAINT; Schema: cleaned; Owner: -
--

ALTER TABLE ONLY cleaned.individual
    ADD CONSTRAINT individual_pk PRIMARY KEY (ind_idn);


--
-- Name: name name_pk; Type: CONSTRAINT; Schema: cleaned; Owner: -
--

ALTER TABLE ONLY cleaned.name
    ADD CONSTRAINT name_pk PRIMARY KEY (nam_idn);


--
-- Name: offense offense_record_pk; Type: CONSTRAINT; Schema: cleaned; Owner: -
--

ALTER TABLE ONLY cleaned.offense
    ADD CONSTRAINT offense_record_pk PRIMARY KEY (offense_record_id);


--
-- Name: person person_pk; Type: CONSTRAINT; Schema: cleaned; Owner: -
--

ALTER TABLE ONLY cleaned.person
    ADD CONSTRAINT person_pk PRIMARY KEY (per_idn);


--
-- Name: idx_address_ind_idn; Type: INDEX; Schema: cleaned; Owner: -
--

CREATE INDEX idx_address_ind_idn ON cleaned.address USING btree (ind_idn);


--
-- Name: idx_name_per_idn; Type: INDEX; Schema: cleaned; Owner: -
--

CREATE INDEX idx_name_per_idn ON cleaned.name USING btree (per_idn);


--
-- Name: idx_offense_cdd_dte; Type: INDEX; Schema: cleaned; Owner: -
--

CREATE INDEX idx_offense_cdd_dte ON cleaned.offense USING btree (cdd_dte);


--
-- Name: idx_offense_ind_idn; Type: INDEX; Schema: cleaned; Owner: -
--

CREATE INDEX idx_offense_ind_idn ON cleaned.offense USING btree (ind_idn);


--
-- Name: idx_person_ind_idn; Type: INDEX; Schema: cleaned; Owner: -
--

CREATE INDEX idx_person_ind_idn ON cleaned.person USING btree (ind_idn);


--
-- Name: address address_individual_fk; Type: FK CONSTRAINT; Schema: cleaned; Owner: -
--

ALTER TABLE ONLY cleaned.address
    ADD CONSTRAINT address_individual_fk FOREIGN KEY (ind_idn) REFERENCES cleaned.individual(ind_idn);


--
-- Name: name name_person_fk; Type: FK CONSTRAINT; Schema: cleaned; Owner: -
--

ALTER TABLE ONLY cleaned.name
    ADD CONSTRAINT name_person_fk FOREIGN KEY (per_idn) REFERENCES cleaned.person(per_idn);


--
-- Name: offense offense_individual_fk; Type: FK CONSTRAINT; Schema: cleaned; Owner: -
--

ALTER TABLE ONLY cleaned.offense
    ADD CONSTRAINT offense_individual_fk FOREIGN KEY (ind_idn) REFERENCES cleaned.individual(ind_idn);


--
-- Name: person person_individual_fk; Type: FK CONSTRAINT; Schema: cleaned; Owner: -
--

ALTER TABLE ONLY cleaned.person
    ADD CONSTRAINT person_individual_fk FOREIGN KEY (ind_idn) REFERENCES cleaned.individual(ind_idn);


--
-- PostgreSQL database dump complete
--

\unrestrict vGoRKqiqpkXBgcpeBElh5KYBsgiGO0u7F1sIA7s2ThnQG9NwCzUouSbtrzx2wkd

