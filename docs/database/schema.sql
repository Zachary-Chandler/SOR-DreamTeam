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
-- Tables below were added by hand to match the DPS table layout
-- (Documentation/Layout.pdf inside the export zip). See docs/database/LAYOUT.md.
--
-- Their foreign keys are DEFERRABLE INITIALLY DEFERRED: apply_removals.py deletes a
-- person's rows table by table in one transaction, and deferred keys are checked only
-- at COMMIT, so the order it deletes in doesn't matter.
--

CREATE TABLE cleaned.birth_date (
    dob_idn text NOT NULL,
    per_idn text,
    typ_cod text,
    dob_dte timestamp without time zone,
    CONSTRAINT birth_date_pk PRIMARY KEY (dob_idn),
    CONSTRAINT birth_date_person_fk FOREIGN KEY (per_idn) REFERENCES cleaned.person(per_idn) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE cleaned.individual_sor (
    ind_idn text NOT NULL,
    dps_nbr text,
    rsk_cod text,
    ssz_cod text,
    swd_cod text,
    ert_cod text,
    erd_dte timestamp without time zone,
    vrp_cod text,
    CONSTRAINT individual_sor_pk PRIMARY KEY (ind_idn),
    CONSTRAINT individual_sor_individual_fk FOREIGN KEY (ind_idn) REFERENCES cleaned.individual(ind_idn) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE cleaned.photo (
    photoid text NOT NULL,
    ind_idn text,
    pos_dte timestamp without time zone,
    CONSTRAINT photo_pk PRIMARY KEY (photoid),
    CONSTRAINT photo_individual_fk FOREIGN KEY (ind_idn) REFERENCES cleaned.individual(ind_idn) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE cleaned.registration_event (
    eventid text NOT NULL,
    ind_idn text,
    evm_cod text,
    evt_dte timestamp without time zone,
    evo_nbr text,
    ori_txt text,
    CONSTRAINT registration_event_pk PRIMARY KEY (eventid),
    CONSTRAINT registration_event_individual_sor_fk FOREIGN KEY (ind_idn) REFERENCES cleaned.individual_sor(ind_idn) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE cleaned.address_event (
    addresseventid text NOT NULL,
    eventid text,
    ind_idn text,
    pdv_cod text,
    addressid text,
    CONSTRAINT address_event_pk PRIMARY KEY (addresseventid),
    CONSTRAINT address_event_registration_event_fk FOREIGN KEY (eventid) REFERENCES cleaned.registration_event(eventid) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT address_event_address_fk FOREIGN KEY (addressid) REFERENCES cleaned.address(addressid) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE cleaned.institute (
    instituteid text NOT NULL,
    ins_cod text,
    ins_txt text,
    CONSTRAINT institute_pk PRIMARY KEY (instituteid)
);

CREATE TABLE cleaned.institute_campus (
    campusid text NOT NULL,
    instituteid text,
    cam_txt text,
    CONSTRAINT institute_campus_pk PRIMARY KEY (campusid),
    CONSTRAINT institute_campus_institute_fk FOREIGN KEY (instituteid) REFERENCES cleaned.institute(instituteid) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE cleaned.education (
    educationid text NOT NULL,
    ind_idn text,
    campusid text,
    emp_flg text,
    stu_flg text,
    uin_txt text,
    ucm_txt text,
    uct_txt text,
    CONSTRAINT education_pk PRIMARY KEY (educationid),
    CONSTRAINT education_individual_fk FOREIGN KEY (ind_idn) REFERENCES cleaned.individual(ind_idn) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT education_institute_campus_fk FOREIGN KEY (campusid) REFERENCES cleaned.institute_campus(campusid) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE cleaned.education_event (
    educationeventid text NOT NULL,
    eventid text,
    ind_idn text,
    pdv_cod text,
    educationid text,
    CONSTRAINT education_event_pk PRIMARY KEY (educationeventid),
    CONSTRAINT education_event_registration_event_fk FOREIGN KEY (eventid) REFERENCES cleaned.registration_event(eventid) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT education_event_education_fk FOREIGN KEY (educationid) REFERENCES cleaned.education(educationid) DEFERRABLE INITIALLY DEFERRED
);

-- License and occupation tables: in the layout, but the current DPS export ships no data
-- for them (only their format files). transform_to_cleaned.py fills them if `sor` ever has
-- the source tables. The real link from license to issuer goes through two more DPS tables
-- (OccupationalLicenseLicenses, OccupationalLicenseCategories), so there is no direct key.
CREATE TABLE cleaned.license_issuers (
    occupationallicenseissuersid text NOT NULL,
    oli_txt text,
    CONSTRAINT license_issuers_pk PRIMARY KEY (occupationallicenseissuersid)
);

CREATE TABLE cleaned.license (
    licenseid text NOT NULL,
    ind_idn text,
    occupationallicenselicensesid text,
    CONSTRAINT license_pk PRIMARY KEY (licenseid),
    CONSTRAINT license_individual_fk FOREIGN KEY (ind_idn) REFERENCES cleaned.individual(ind_idn) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE cleaned.license_event (
    licenseeventid text NOT NULL,
    eventid text,
    ind_idn text,
    pdv_cod text,
    licenseid text,
    CONSTRAINT license_event_pk PRIMARY KEY (licenseeventid),
    CONSTRAINT license_event_registration_event_fk FOREIGN KEY (eventid) REFERENCES cleaned.registration_event(eventid) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT license_event_license_fk FOREIGN KEY (licenseid) REFERENCES cleaned.license(licenseid) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE cleaned.occupation (
    occupationid text NOT NULL,
    ind_idn text,
    emp_txt text,
    snu_nbr text,
    sna_txt text,
    cty_txt text,
    sta_cod text,
    zip_txt text,
    occ_txt text,
    occ_cod text,
    CONSTRAINT occupation_pk PRIMARY KEY (occupationid),
    CONSTRAINT occupation_individual_fk FOREIGN KEY (ind_idn) REFERENCES cleaned.individual(ind_idn) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE cleaned.occupation_event (
    occupationeventid text NOT NULL,
    eventid text,
    ind_idn text,
    pdv_cod text,
    occupationid text,
    CONSTRAINT occupation_event_pk PRIMARY KEY (occupationeventid),
    CONSTRAINT occupation_event_registration_event_fk FOREIGN KEY (eventid) REFERENCES cleaned.registration_event(eventid) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT occupation_event_occupation_fk FOREIGN KEY (occupationid) REFERENCES cleaned.occupation(occupationid) DEFERRABLE INITIALLY DEFERRED
);

-- Offense code lookup. The raw table has exact duplicate rows and some null code parts,
-- so it gets a surrogate key like cleaned.offense. A few offenses use codes that are not
-- in this table, so there is no foreign key from offense; join on the five code columns.
CREATE TABLE cleaned.off_code_sor (
    off_code_record_id bigint GENERATED ALWAYS AS IDENTITY,
    coo_cod text,
    coj_cod text,
    joo_cod text,
    off_cod text,
    ver_nbr text,
    len_txt text,
    sts_cod text,
    cit_txt text,
    begindate timestamp without time zone,
    enddate timestamp without time zone,
    CONSTRAINT off_code_sor_pk PRIMARY KEY (off_code_record_id)
);

-- Code lookup tables (literals for the *_COD fields).
CREATE TABLE cleaned.table_codes (
    schemaname text NOT NULL,
    tbl_cod text NOT NULL,
    col_cod text NOT NULL,
    val_cod text NOT NULL,
    val_txt text,
    fkref text,
    CONSTRAINT table_codes_pk PRIMARY KEY (schemaname, tbl_cod, col_cod, val_cod)
);

CREATE TABLE cleaned.tbl (
    tbl_idn text NOT NULL,
    tbl_cod text,
    tbl_txt text,
    inq_txt text,
    upd_txt text,
    batch_id text,
    CONSTRAINT tbl_pk PRIMARY KEY (tbl_idn)
);

CREATE TABLE cleaned.col (
    col_idn text NOT NULL,
    tbl_idn text,
    col_cod text,
    col_txt text,
    batch_id text,
    CONSTRAINT col_pk PRIMARY KEY (col_idn),
    CONSTRAINT col_tbl_fk FOREIGN KEY (tbl_idn) REFERENCES cleaned.tbl(tbl_idn) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE cleaned.val (
    val_idn text NOT NULL,
    col_idn text,
    val_cod text,
    val_txt text,
    act_cod text,
    lng_txt text,
    app_cod text,
    batch_id text,
    CONSTRAINT val_pk PRIMARY KEY (val_idn),
    CONSTRAINT val_col_fk FOREIGN KEY (col_idn) REFERENCES cleaned.col(col_idn) DEFERRABLE INITIALLY DEFERRED
);

-- Some VAL_RELN rows point at VAL entries DPS no longer ships, so no foreign keys here;
-- lookup rows are kept as-is rather than dropped.
CREATE TABLE cleaned.val_reln (
    vlr_idn text NOT NULL,
    val_idn text,
    var_idn text,
    cmb_cod text,
    batch_id text,
    CONSTRAINT val_reln_pk PRIMARY KEY (vlr_idn)
);

-- NCIC place codes. place_code_types is in the layout but not in the export, so it stays
-- empty and place_codes has no foreign key to it.
CREATE TABLE cleaned.place_code_types (
    plt_cod text NOT NULL,
    plt_txt text,
    CONSTRAINT place_code_types_pk PRIMARY KEY (plt_cod)
);

CREATE TABLE cleaned.place_codes (
    plt_cod text NOT NULL,
    plc_cod text NOT NULL,
    plc_txt text,
    CONSTRAINT place_codes_pk PRIMARY KEY (plt_cod, plc_cod)
);

CREATE INDEX idx_birth_date_per_idn ON cleaned.birth_date USING btree (per_idn);
CREATE INDEX idx_photo_ind_idn ON cleaned.photo USING btree (ind_idn);
CREATE INDEX idx_registration_event_ind_idn ON cleaned.registration_event USING btree (ind_idn);
CREATE INDEX idx_address_event_eventid ON cleaned.address_event USING btree (eventid);
CREATE INDEX idx_address_event_addressid ON cleaned.address_event USING btree (addressid);
CREATE INDEX idx_address_event_ind_idn ON cleaned.address_event USING btree (ind_idn);
CREATE INDEX idx_education_ind_idn ON cleaned.education USING btree (ind_idn);
CREATE INDEX idx_education_event_eventid ON cleaned.education_event USING btree (eventid);
CREATE INDEX idx_education_event_ind_idn ON cleaned.education_event USING btree (ind_idn);
CREATE INDEX idx_license_ind_idn ON cleaned.license USING btree (ind_idn);
CREATE INDEX idx_license_event_ind_idn ON cleaned.license_event USING btree (ind_idn);
CREATE INDEX idx_occupation_ind_idn ON cleaned.occupation USING btree (ind_idn);
CREATE INDEX idx_occupation_event_ind_idn ON cleaned.occupation_event USING btree (ind_idn);
CREATE INDEX idx_off_code_sor_code ON cleaned.off_code_sor USING btree (coo_cod, coj_cod, joo_cod, off_cod, ver_nbr);

-- Photos are not stored. DPS serves each registrant's current photo from its public site,
-- keyed by DPS number, so the app puts photo_url in an <img> tag and the browser loads it
-- from DPS. has_photo comes from the export; DPS returns 404 when there is no photo.
-- See docs/database/PHOTOS.md.
CREATE VIEW cleaned.individual_photo AS
 SELECT i.ind_idn,
    i.dps_nbr,
    ('https://sor.dps.texas.gov/Search/Rapsheet/CurrentPhoto?sid='::text || lpad(btrim(i.dps_nbr), 8, '0'::text)) AS photo_url,
    (EXISTS ( SELECT 1
           FROM cleaned.photo p
          WHERE (p.ind_idn = i.ind_idn))) AS has_photo,
    ( SELECT max(p.pos_dte) AS max
           FROM cleaned.photo p
          WHERE (p.ind_idn = i.ind_idn)) AS latest_photo_date
   FROM cleaned.individual i;


--
-- PostgreSQL database dump complete
--

\unrestrict vGoRKqiqpkXBgcpeBElh5KYBsgiGO0u7F1sIA7s2ThnQG9NwCzUouSbtrzx2wkd

