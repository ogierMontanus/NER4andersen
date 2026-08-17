<?xml version="1.0" encoding="UTF-8"?>
<!--
    extract-comments.xsl  —  STEP 1

    Extract *every* editorial comment from a svNames Andersen volume, with the
    context needed downstream: page, enclosing work, and the work's year.

    A volume encodes each comment twice:

      (a) the printed apparatus, at the end of the volume:
          <table rend="textcomments">
            <cell type="page">12</cell>
            <row xml:id="txtcmnt-012-01">
              <cell type="data-term">…lemma…</cell>
              <cell type="data-definition">…explanation…</cell>
            </row>

      (b) the same comment injected inline into the running text:
          <seg target="txtcmnt-012-01">
            <data-term>…</data-term><data-definition>…</data-definition>…</seg>

    (a) is authoritative (it is the complete apparatus); (b) is what anchors a
    comment inside a particular work, and therefore what dates it. We emit one
    <comment> per apparatus row, enriched from the inline anchor, and then any
    inline-only comment that has no apparatus row, so nothing is dropped.

    YEAR RESOLUTION — strictly from metadata in the file:
      * major works  : div[@type='work']/front//docImprint     (1851, 1863, 1868)
      * minor works  : div[@type='work']/div[@type='source']/sourceDate
    The work is found from the inline anchor's ancestor work; if a row has no
    inline anchor we fall back to the work containing that printed page (pb/@n).

    Usage:
      java -cp saxon.jar net.sf.saxon.Transform \
           -s:"Andersen 15 - …xml" -xsl:extract-comments.xsl -o:out/comments.xml
    Optional: -volume:15  (otherwise taken from the title)
-->
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:xs="http://www.w3.org/2001/XMLSchema"
                xmlns:f="urn:svnames:placenames"
                xpath-default-namespace="http://www.tei-c.org/ns/1.0"
                exclude-result-prefixes="#all"
                version="3.0">

    <xsl:output method="xml" indent="yes" encoding="UTF-8"/>
    <xsl:strip-space elements="*"/>

    <!-- volume number; default: first integer in the <title> -->
    <xsl:param name="volume" as="xs:string" select="''"/>

    <xsl:key name="seg-by-target" match="seg[@target]" use="normalize-space(@target)"/>
    <xsl:key name="pb-by-n"       match="pb[@n]"       use="normalize-space(@n)"/>
    <xsl:key name="row-by-id"     match="row[@xml:id]" use="normalize-space(@xml:id)"/>

    <!-- ===================== helper functions ===================== -->

    <!-- plain text of a node, whitespace-normalised -->
    <xsl:function name="f:text" as="xs:string">
        <xsl:param name="n" as="node()?"/>
        <xsl:sequence select="normalize-space(string-join($n//text(), ''))"/>
    </xsl:function>

    <!-- Page encoded in a comment id. Two schemes are in use:
           txtcmnt-012-01      page-seq          (vols 1-16)
           txtcmnt-17-013-01   volume-page-seq   (vols 17-18)
         In both the page is the second-to-last numeric part, so take that
         rather than the first number (which is the volume in the long form). -->
    <xsl:function name="f:page-from-id" as="xs:string">
        <xsl:param name="id" as="xs:string"/>
        <xsl:variable name="nums"
                      select="tokenize(replace($id, '^.*txtcmnt-', ''), '-')[matches(., '^\d+$')]"/>
        <xsl:sequence select="
            if (count($nums) ge 2) then string(xs:integer($nums[last() - 1]))
            else if (count($nums) eq 1) then string(xs:integer($nums[1]))
            else ''"/>
    </xsl:function>

    <!-- the work a comment belongs to: inline anchor first, page fallback -->
    <xsl:function name="f:work" as="element(div)?">
        <xsl:param name="id"   as="xs:string"/>
        <xsl:param name="page" as="xs:string"/>
        <xsl:param name="ctx"  as="node()"/>
        <xsl:variable name="viaSeg"
                      select="key('seg-by-target', $id, root($ctx))[1]
                              /ancestor::div[@type='work'][1]"/>
        <xsl:variable name="viaPage"
                      select="(key('pb-by-n', $page, root($ctx))
                               [ancestor::div[@type='work']])[1]
                              /ancestor::div[@type='work'][1]"/>
        <xsl:sequence select="($viaSeg, $viaPage)[1]"/>
    </xsl:function>

    <!-- The work's year, taken only from metadata. Two layouts occur:
           * travel accounts / autobiographies — the source block is a CHILD of the
             work:      <div type="work"><div type="source">…<sourceDate>1857
             and the three major books carry <front>…<docImprint>1851
           * tales / poems — the source block WRAPS a whole booklet and the
             individual works are its children:
                        <div type="source"><sourceTitle>Eventyr…<sourceDate>1835
                          <div type="work">…Fyrtøiet…
             so the date must be inherited from the ancestor.                      -->
    <xsl:function name="f:year" as="xs:string">
        <xsl:param name="work" as="element(div)?"/>
        <xsl:variable name="raw" as="xs:string" select="(
            f:text(($work/front//docImprint)[1])[. ne ''],
            f:text(($work/div[@type='source']/sourceDate)[1])[. ne ''],
            f:text(($work/ancestor::div[@type='source'][1]/sourceDate)[1])[. ne ''],
            f:text(($work//docImprint)[1])[. ne ''],
            f:text(($work//sourceDate)[1])[. ne ''],
            '')[1]"/>
        <!-- The date field is not always a bare year: the Skuespil volumes write
             prose such as "Opført første gang 5. maj 1832". Take the first
             maximal run of exactly four digits rather than regex-replacing, which
             silently returns the whole sentence when the pattern does not match. -->
        <xsl:sequence select="(tokenize($raw, '\D+')[matches(., '^\d{4}$')], '')[1]"/>
    </xsl:function>

    <!-- a human label for the work -->
    <xsl:function name="f:work-title" as="xs:string">
        <xsl:param name="work" as="element(div)?"/>
        <xsl:sequence select="(f:text(($work//titlePart[@type='main'])[1])[. ne ''],
                               f:text(($work/head[@type='main'])[1])[. ne ''],
                               f:text(($work/div[@type='source']/sourceTitle)[1])[. ne ''],
                               f:text(($work/ancestor::div[@type='source'][1]/sourceTitle)[1])[. ne ''],
                               f:text(($work//sourceTitle)[1])[. ne ''],
                               '(untitled)')[1]"/>
    </xsl:function>

    <!-- ===================== main ===================== -->

    <xsl:template match="/">
        <xsl:variable name="title" select="f:text((//teiHeader//titleStmt/title)[1])"/>
        <!-- Volume number: the explicit parameter, else the header title, else the
             file name. Vols 2 and 4 carry an empty <title> </title>, so without the
             file-name fallback their comments would be emitted with no volume and
             would not group correctly in a merged index. -->
        <xsl:variable name="uri" select="string((document-uri(/), base-uri(/))[1])"/>
        <xsl:variable name="vol" as="xs:string" select="(
            $volume[. ne ''],
            tokenize($title, '\D+')[. ne ''][1],
            (if (matches($uri, 'Andersen(%20|[\s_])+\d+'))
             then replace($uri, '^.*Andersen(?:%20|[\s_])+(\d+).*$', '$1') else ()),
            '')[1]"/>

        <!-- Apparatus rows carrying an actual comment.
             Descendant axis, not a child step: some volumes (8-13) wrap every
             row in an extra untyped <cell>, so <table>/<row> would find nothing. -->
        <xsl:variable name="rows"
                      select="//table[@rend='textcomments']
                              //row[cell[@type='data-term'] or cell[@type='data-definition']]"/>
        <!-- inline comments with no apparatus row (nothing may be lost) -->
        <xsl:variable name="orphanSegs"
                      select="//seg[@target][data-term or data-definition]
                              [not(key('row-by-id', normalize-space(@target)))]"/>

        <comments volume="{$vol}" title="{$title}"
                  count="{count($rows) + count($orphanSegs)}"
                  fromApparatus="{count($rows)}" inlineOnly="{count($orphanSegs)}">

            <xsl:for-each select="$rows">
                <xsl:variable name="id"   select="normalize-space(@xml:id)"/>
                <!-- the id encodes the page (txtcmnt-045-01 -> 45) and survives the
                     differing table nestings; the page cell is only a fallback -->
                <xsl:variable name="page" as="xs:string" select="
                    (f:page-from-id($id)[. ne ''],
                     f:text((preceding::cell[@type='page'])[last()])[. ne ''],
                     '')[1]"/>
                <xsl:variable name="work" select="f:work($id, $page, .)"/>
                <comment id="{$id}" page="{$page}"
                         year="{f:year($work)}" work="{f:work-title($work)}"
                         anchored="{exists(key('seg-by-target', $id))}" src="apparatus">
                    <lemma><xsl:value-of select="f:text(cell[@type='data-term'])"/></lemma>
                    <definition><xsl:value-of select="f:text(cell[@type='data-definition'])"/></definition>
                </comment>
            </xsl:for-each>

            <xsl:for-each select="$orphanSegs">
                <xsl:variable name="id"   select="normalize-space(@target)"/>
                <xsl:variable name="page" as="xs:string" select="
                    (normalize-space((preceding::pb[@n])[last()]/@n),
                     f:page-from-id($id), '')[1]"/>
                <xsl:variable name="work" select="ancestor::div[@type='work'][1]"/>
                <comment id="{$id}" page="{$page}"
                         year="{f:year($work)}" work="{f:work-title($work)}"
                         anchored="true" src="inline">
                    <lemma><xsl:value-of select="f:text(data-term)"/></lemma>
                    <definition><xsl:value-of select="f:text(data-definition)"/></definition>
                </comment>
            </xsl:for-each>
        </comments>
    </xsl:template>

</xsl:stylesheet>
