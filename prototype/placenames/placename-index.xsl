<?xml version="1.0" encoding="UTF-8"?>
<!--
    placename-index.xsl  —  STEPS 2 & 3

    Input : out/comments-vol15.xml  (produced by extract-comments.xsl)
    Output: (a) $categorized  — every comment tagged with place category,
                                evidence and confidence            [STEP 2 review]
            (b) principal     — the deduplicated place-name index   [STEP 3]

    STEP 2 — categorisation. A comment is judged against five independent
    signals, all derived from the Danish editorial prose:

      in-register  the lemma matches svNames data/registers/places.xml
      se-kort      the note carries a map cross-reference ("se kort 2") — in this
                   edition only places are mapped, so this is a very strong signal
      head-noun    the definition *opens* with a geographic head-noun, i.e. it
                   predicates a place: "by i Indien", "landskab i Sverige",
                   "karteuserkloster fra 1516". This is what separates a real
                   place note from a vocabulary gloss that merely contains a
                   geographic word ("kvindelig forstander for et nonnekloster")
      located      a lower-case head-noun followed by a spatial preposition and a
                   proper noun ("flod … gennem Rom")
      place-type   a geographic word occurs anywhere near the start (weak)

    All matching is on whole words, never substrings: "på" must not match the
    type "å", "selv" must not match "elv", and the surname "Vidal" must not match
    the compound tail "dal".

    Parenthesised life-dates in the opening — "(1796-1868), svensk forfatter" —
    mark a PERSON and veto the place reading unless the lemma is in the register.

    Confidence: high   = in-register | se-kort | head-noun
                medium = located
                low    = only a generic geographic word, or a person note that
                         merely mentions somewhere (kept, flagged for review)

    STEP 3 — the index takes high+medium, suppresses duplicates by normalised
    name, and carries the YEAR through from the work metadata resolved in step 1
    (docImprint / sourceDate). Where the note supplies a modern normalised
    spelling ("Calmar" -> "Kalmar; se kort 1.") that becomes the index headword
    and Andersen's spelling is kept as the variant.

    Usage:
      java -cp saxon.jar net.sf.saxon.Transform \
        -s:out/comments-vol15.xml -xsl:placename-index.xsl \
        -o:out/placenames-vol15.tsv \
        register=/path/to/svNames/data/registers/places.xml \
        categorized=out/comments-vol15-categorized.xml
-->
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:xs="http://www.w3.org/2001/XMLSchema"
                xmlns:f="urn:svnames:placenames"
                exclude-result-prefixes="#all"
                version="3.0">

    <xsl:output method="text" encoding="UTF-8"/>
    <xsl:output name="xml" method="xml" indent="yes" encoding="UTF-8"/>

    <xsl:param name="register" as="xs:string"
               select="'/home/user/svNames/data/registers/places.xml'"/>
    <xsl:param name="categorized" as="xs:string" select="'comments-categorized.xml'"/>
    <!-- Optional: semicolon-separated list of further comments.xml files. When
         given, the index is built over the union of the principal input and
         these, so one place occurring in several volumes stays a single entry
         and simply accumulates occurrences, years, volumes and spellings. -->
    <xsl:param name="sources" as="xs:string" select="''"/>
    <!-- how far into the definition a head-noun still describes the lemma -->
    <xsl:param name="head-window" as="xs:integer" select="80"/>

    <!-- ============ vocabulary ============ -->

    <!-- geographic head-nouns, incl. Danish definite/plural forms -->
    <xsl:variable name="TYPES" as="xs:string">by|byen|byer|byerne|købstad|købstaden|hovedstad|hovedstaden|landsby|landsbyen|flække|provins|provinsen|landskab|landskabet|region|regionen|amt|amtet|herred|herredet|sogn|sognet|distrikt|distriktet|ø|øen|øer|øerne|øgruppe|halvø|halvøen|holm|holmen|flod|floden|elv|elven|å|åen|sund|sundet|fjord|fjorden|bugt|bugten|hav|havet|sø|søen|kanal|kanalen|vig|vigen|stræde|strædet|bjerg|bjerget|bjerge|bjergene|bjergkæde|bakke|bakken|dal|dalen|klippe|klippen|plateau|vulkan|skov|skoven|hede|heden|slette|sletten|ørken|ørkenen|gade|gaden|torv|torvet|plads|pladsen|allé|bro|broen|havn|havnen|kaj|promenade|slot|slottet|borg|borgen|palads|paladset|kloster|klosteret|klostret|kirke|kirken|domkirke|domkirken|katedral|katedralen|tårn|tårnet|fæstning|fæstningen|citadel|ruin|ruiner|ruinerne|kilde|kilden|gods|godset|herregård|hovedgård|hovedgårde|forstad|forstaden|bydel|bydelen|kvarter|kvarteret|residensslot|kongerige|kongeriget|republik|republikken|koloni|hertugdømme|grevskab|næs|odde|kyst|kysten|vandfald|flodmunding</xsl:variable>

    <!-- heads that may appear as the tail of a compound (havneby, domkirke …) -->
    <xsl:variable name="COMP" as="xs:string">by|byen|kirke|kirken|kloster|klosteret|klostret|bjerg|bjerget|bjergene|havn|havnen|gade|gaden|torv|torvet|slot|slottet|borg|borgen|flod|floden|dal|dalen|hav|havet|sund|sundet|fjord|fjorden|halvø|halvøen</xsl:variable>

    <xsl:variable name="PREP" as="xs:string">i|på|ved|nær|fra|til|mellem|gennem|omkring|uden for|nord for|syd for|øst for|vest for|nordøst for|nordvest for|sydøst for|sydvest for</xsl:variable>

    <!-- determiners/adjectives tolerated before the defining head-noun -->
    <xsl:variable name="LEAD" as="xs:string">(den|det|de|en|et|denne|dette|hele|nuværende|gamle|lille|store|\p{L}+ste|\p{L}+e)</xsl:variable>

    <!-- XPath regex has no \b: use explicit non-letter boundaries -->
    <xsl:variable name="NL" as="xs:string">[^\p{L}\p{N}]</xsl:variable>

    <xsl:variable name="RE-TYPE"  select="concat('(^|', $NL, ')(', $TYPES, ')($|', $NL, ')')"/>
    <xsl:variable name="RE-COMP"  select="concat('(^|', $NL, ')\p{L}+(', $COMP, ')($|', $NL, ')')"/>
    <!-- the definition *opens* with a geographic head-noun => it defines a place -->
    <xsl:variable name="RE-HEAD"
        select="concat('^(', $LEAD, '\s+){0,3}(\p{L}*(', $COMP, ')|(', $TYPES, '))($|', $NL, ')')"/>
    <!-- head-noun followed by a spatial preposition and a proper noun.
         The head-noun must be LOWER-CASE here: it has to be a common noun, or a
         surname that merely ends in one ("Vi|dal", "Bangs|bo") produces a match. -->
    <xsl:variable name="RE-LOC"
        select="concat('((^|', $NL, ')(', $TYPES, ')|(^|', $NL, ')\p{Ll}+(', $COMP,
                       '))\P{Lu}{0,28}(', $PREP, ')\s+\p{Lu}')"/>
    <!-- parenthesised life-dates anywhere early => the note describes a PERSON -->
    <xsl:variable name="RE-PERSON" as="xs:string">\(\s*(([dfDF]\.\s*\d{3,4})|(\d{3,4}\s*[-–]\s*\d{0,4}))\s*\)</xsl:variable>
    <xsl:variable name="RE-KORT"   as="xs:string">se\s+kort</xsl:variable>

    <!-- ============ helpers ============ -->

    <!-- comparison key: drop parentheses/punctuation, fold case -->
    <xsl:function name="f:norm" as="xs:string">
        <xsl:param name="s" as="xs:string?"/>
        <xsl:sequence select="normalize-space(
            lower-case(replace(replace($s, '\([^)]*\)', ''), '[.,;:!?«»&quot;''’\[\]]', ' ')))"/>
    </xsl:function>

    <!-- make a value safe to drop into a tab-separated field -->
    <xsl:function name="f:tsv" as="xs:string">
        <xsl:param name="s" as="xs:string?"/>
        <xsl:sequence select="normalize-space(translate(string($s), '&#9;&#10;&#13;', '   '))"/>
    </xsl:function>

    <!-- display form: "Halland(s)" -> "Halland" -->
    <xsl:function name="f:clean" as="xs:string">
        <xsl:param name="s" as="xs:string?"/>
        <xsl:sequence select="normalize-space(
            replace(replace($s, '\([^)]*\)', ''), '^[\s,;:.]+|[\s,;:.]+$', ''))"/>
    </xsl:function>

    <!-- definition body: drop a leading parenthetical "(1796-1868), " / "(spansk) "
         and a leading normalised headword "Kalmar; ", so that what remains starts
         with the words that actually define the lemma -->
    <xsl:function name="f:body" as="xs:string">
        <xsl:param name="d" as="xs:string"/>
        <xsl:sequence select="normalize-space(
            replace(
              replace($d, '^\s*\([^)]*\)\s*,?\s*', ''),
              '^\s*\p{Lu}[^;]{0,38};\s*', ''))"/>
    </xsl:function>

    <!-- the first $w characters of the body -->
    <xsl:function name="f:head" as="xs:string">
        <xsl:param name="d" as="xs:string"/>
        <xsl:param name="w" as="xs:integer"/>
        <xsl:sequence select="substring(f:body($d), 1, $w)"/>
    </xsl:function>

    <!-- modern spelling the note may open with: "Kalmar; se kort 1." -->
    <xsl:function name="f:normalised-name" as="xs:string">
        <xsl:param name="d" as="xs:string"/>
        <xsl:variable name="m"
            select="if (matches($d, '^\s*\p{Lu}[\p{L}\-’''\.]*(\s+(de|del|la|le|el|di|da|von|van|af))?(\s+\p{Lu}[\p{L}\-’''\.]*)*\s*[;,]'))
                    then replace($d, '^\s*(.*?)\s*[;,].*$', '$1') else ''"/>
        <xsl:sequence select="if (matches($m, '^\p{Lu}') and string-length($m) le 40) then $m else ''"/>
    </xsl:function>

    <!-- ============ register ============ -->

    <xsl:variable name="reg-doc" select="if (doc-available($register)) then doc($register) else ()"/>
    <!-- one key entry per placeName variant (main / sort / variant) -->
    <xsl:key name="reg-by-name"
             match="*:place" use="for $n in *:placeName return f:norm($n)"/>

    <xsl:function name="f:geo" as="xs:string">
        <xsl:param name="name" as="xs:string"/>
        <xsl:sequence select="
            if (empty($reg-doc) or $name eq '') then ''
            else string((key('reg-by-name', $name, $reg-doc)/@xml:id)[1])"/>
    </xsl:function>

    <!-- ============ classification (STEP 2) ============ -->

    <xsl:function name="f:evidence" as="xs:string*">
        <xsl:param name="lemma" as="xs:string"/>
        <xsl:param name="def"   as="xs:string"/>
        <xsl:variable name="body" select="f:body($def)"/>
        <xsl:variable name="head" select="f:head($def, $head-window)"/>
        <xsl:sequence select="(
            if (f:geo(f:norm($lemma)) ne '') then 'in-register' else (),
            if (matches($def,  $RE-KORT, 'i'))  then 'se-kort'    else (),
            if (matches($body, $RE-HEAD, 'i'))  then 'head-noun'  else (),
            if (matches($head, $RE-LOC,  'i'))  then 'located'    else (),
            if (matches($head, $RE-TYPE, 'i') or matches($head, $RE-COMP, 'i'))
                then 'place-type' else ()
        )"/>
    </xsl:function>

    <!-- high   : the note defines a place, maps it, or the lemma is in the register
         medium : a head-noun is located against a proper noun
         low    : only a generic geographic word, or a person note that merely
                  mentions somewhere — kept in the categorisation, out of the index -->
    <xsl:function name="f:confidence" as="xs:string">
        <xsl:param name="ev" as="xs:string*"/>
        <xsl:param name="person" as="xs:boolean"/>
        <xsl:sequence select="
            if (empty($ev)) then 'none'
            else if ($person and not('in-register' = $ev)) then 'low'
            else if (some $e in $ev satisfies $e = ('in-register','se-kort','head-noun')) then 'high'
            else if ('located' = $ev) then 'medium'
            else 'low'"/>
    </xsl:function>

    <!-- ============ main ============ -->

    <xsl:template match="/">
        <!-- principal input plus any extra volumes named in $sources -->
        <xsl:variable name="docs" as="document-node()*"
                      select="(/, for $p in tokenize($sources, '\s*;\s*')[. ne '']
                                  return doc($p))"/>
        <xsl:variable name="vol"
                      select="string-join(distinct-values($docs/comments/@volume), ' ')"/>

        <!-- annotate every comment -->
        <xsl:variable name="tagged" as="element(c)*">
            <xsl:for-each select="$docs/comments/comment">
                <xsl:variable name="lemma" select="string(lemma)"/>
                <xsl:variable name="def"   select="string(definition)"/>
                <xsl:variable name="person" select="matches(substring($def,1,110), $RE-PERSON)"/>
                <xsl:variable name="ev"   select="f:evidence($lemma, $def)"/>
                <xsl:variable name="conf" select="f:confidence($ev, $person)"/>
                <xsl:variable name="modern" select="f:normalised-name($def)"/>
                <xsl:variable name="head"   select="if ($modern ne '') then $modern else f:clean($lemma)"/>
                <!-- @lemma keeps Andersen's spelling exactly as printed in the
                     seg/data-term ("Halland(s)", "Calmar"); @variant is the
                     cleaned form used for comparison. The element content is the
                     editorial explanation. -->
                <c id="{@id}" vol="{ancestor::comments/@volume}"
                   page="{@page}" year="{@year}" work="{@work}"
                   conf="{$conf}" evidence="{string-join($ev, '+')}"
                   person="{$person}" place="{$head}"
                   lemma="{$lemma}" variant="{f:clean($lemma)}"
                   key="{f:norm($head)}" geo="{f:geo(f:norm($head))}">
                    <xsl:value-of select="$def"/>
                </c>
            </xsl:for-each>
        </xsl:variable>

        <!-- (a) STEP 2 deliverable: full reviewable categorisation -->
        <xsl:result-document href="{$categorized}" format="xml">
            <categorized volume="{$vol}" comments="{count($tagged)}"
                         high="{count($tagged[@conf='high'])}"
                         medium="{count($tagged[@conf='medium'])}"
                         low="{count($tagged[@conf='low'])}"
                         notPlace="{count($tagged[@conf='none'])}">
                <xsl:sequence select="$tagged[@conf ne 'none']"/>
            </categorized>
        </xsl:result-document>

        <!-- (b) STEP 3 deliverable: deduplicated index, TSV -->
        <xsl:variable name="idx" select="$tagged[@conf = ('high','medium')][@key ne '']"/>
        <xsl:text>place&#9;lemma_andersen&#9;explanation&#9;year&#9;years&#9;volumes&#9;work&#9;page&#9;occurrences&#9;references&#9;confidence&#9;evidence&#9;geo_id&#10;</xsl:text>
        <xsl:for-each-group select="$idx" group-by="@key">
            <xsl:sort select="f:norm(current-group()[1]/@place)"/>
            <!-- earliest reference wins the headline year/work/page -->
            <!-- the main entry is the earliest reference: year, then volume, then page -->
            <xsl:variable name="first" as="element(c)">
                <xsl:sequence select="sort(current-group(), (), function($c) {
                    (if ($c/@year ne '') then xs:integer($c/@year) else 9999) * 10000000
                    + (if ($c/@vol  ne '') then xs:integer($c/@vol)  else 99) * 100000
                    + (if ($c/@page ne '') then xs:integer($c/@page) else 99999)
                })[1]"/>
            </xsl:variable>
            <xsl:variable name="years" select="distinct-values(current-group()/@year[. ne ''])"/>
            <!-- every distinct spelling Andersen actually uses, earliest note first -->
            <xsl:variable name="lemmas"
                          select="distinct-values(current-group()/@lemma[. ne ''])"/>
            <!-- the editorial explanation(s) behind the entry -->
            <xsl:variable name="expl"
                          select="distinct-values(current-group()!f:tsv(string(.))[. ne ''])"/>
            <!-- every occurrence as vol:page (year), earliest first -->
            <xsl:variable name="refs" select="sort(current-group(), (), function($c) {
                    (if ($c/@year ne '') then xs:integer($c/@year) else 9999) * 10000000
                    + (if ($c/@vol  ne '') then xs:integer($c/@vol)  else 99) * 100000
                    + (if ($c/@page ne '') then xs:integer($c/@page) else 99999)
                })!concat('v', @vol, ':', @page, ' (', @year, ')')"/>
            <xsl:value-of select="string-join((
                f:tsv($first/@place),
                string-join($lemmas!f:tsv(.), ' | '),
                string-join($expl, ' ¶ '),
                $first/@year,
                string-join(sort($years), ' '),
                string-join(sort(distinct-values(current-group()/@vol[. ne ''])), ' '),
                f:tsv($first/@work),
                $first/@page,
                string(count(current-group())),
                string-join($refs, '; '),
                (if (current-group()/@conf = 'high') then 'high' else 'medium'),
                string-join(distinct-values(tokenize(string-join(current-group()/@evidence,'+'),'\+')[. ne '']), '+'),
                $first/@geo), '&#9;')"/>
            <xsl:text>&#10;</xsl:text>
        </xsl:for-each-group>
    </xsl:template>

</xsl:stylesheet>
