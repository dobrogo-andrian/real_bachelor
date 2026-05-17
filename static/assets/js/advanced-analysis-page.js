const session = window.CommentLabSession;
            const advancedQueryForm = document.getElementById('advanced-query-form');
            const resetFiltersButton = document.getElementById('reset-filters');
            const queryStatus = document.getElementById('query-status');
            const appliedFiltersContainer = document.getElementById('applied-filters');
            const previewTableBody = document.getElementById('preview-table-body');
            const sqlPreview = document.getElementById('sql-preview');
            const pageNameInputs = Array.from(document.querySelectorAll('input[name="page_name"]'));
            const pageIdInputs = Array.from(document.querySelectorAll('input[name="page_id"]'));
            const chartStatus = document.getElementById('chart-status');
            const advancedChartRoot = document.getElementById('advanced-chart-root');
            const queryPreviewSection = document.getElementById('query-preview-section');
            const previewExpandWrap = document.getElementById('preview-expand-wrap');
            const togglePreviewRowsButton = document.getElementById('toggle-preview-rows');
            const queryLoading = document.getElementById('query-loading');

            let previewRowsState = {
                rows: [],
                expanded: false
            };

            const summaryTotalComments = document.getElementById('summary-total-comments');
            const summaryDistinctPosts = document.getElementById('summary-distinct-posts');
            const summaryAverageLikes = document.getElementById('summary-average-likes');

            function toSqlDatetime(value) {
                return value ? value.replace('T', ' ') : '';
            }

            function buildPayload() {
                if (!advancedQueryForm) {
                    return {};
                }

                const payload = {};
                const multiSelectNames = ['page_name', 'page_id', 'source', 'language', 'sentiment', 'first_comment_sentiment'];

                multiSelectNames.forEach((name) => {
                    const values = Array.from(advancedQueryForm.querySelectorAll(`input[name="${name}"]:checked`))
                        .map((input) => input.value.trim())
                        .filter((value) => value !== '__all__')
                        .filter(Boolean);
                    if (values.length) {
                        payload[name] = values;
                    }
                });

                const formData = new FormData(advancedQueryForm);

                formData.forEach((value, key) => {
                    if (multiSelectNames.includes(key)) {
                        return;
                    }
                    const normalizedValue = typeof value === 'string' ? value.trim() : value;
                    if (!normalizedValue) {
                        return;
                    }

                    if (key === 'post_time_from' || key === 'post_time_to' || key === 'comment_time_from' || key === 'comment_time_to') {
                        payload[key] = toSqlDatetime(normalizedValue);
                        return;
                    }

                    payload[key] = normalizedValue;
                });

                return payload;
            }

            function renderAppliedFilters(filters) {
                appliedFiltersContainer.innerHTML = '';
                const entries = Object.entries(filters || {});
                const filterLabels = {
                    first_comment_sentiment: 'post description sentiment'
                };
                if (!entries.length) {
                    appliedFiltersContainer.innerHTML = '<span class="chip">No filters applied</span>';
                    return;
                }

                entries.forEach(([key, value]) => {
                    const chip = document.createElement('span');
                    chip.className = 'chip';
                    const label = filterLabels[key] || key;
                    chip.textContent = `${label}: ${Array.isArray(value) ? value.join(', ') : value}`;
                    appliedFiltersContainer.appendChild(chip);
                });
            }

            function escapeHtml(value) {
                return String(value ?? '')
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#039;');
            }

            function renderRows(rows) {
                previewRowsState.rows = Array.isArray(rows) ? rows : [];
                if (!rows || !rows.length) {
                    previewTableBody.innerHTML = '<tr><td colspan="8">No matching rows for the current filter set.</td></tr>';
                    previewRowsState.expanded = false;
                    if (previewExpandWrap) {
                        previewExpandWrap.hidden = true;
                    }
                    return;
                }

                const visibleRows = previewRowsState.expanded ? rows : rows.slice(0, 5);
                previewTableBody.innerHTML = visibleRows.map((row) => `
                    <tr>
                        <td>${escapeHtml(row.PageName || row.PageID || '-')}</td>
                        <td>${row.PostHref ? `<a class="analysis-post-link" href="${escapeHtml(row.PostHref)}" target="_blank" rel="noopener noreferrer">${escapeHtml(row.PostTime || '-')}</a>` : escapeHtml(row.PostTime || '-')}</td>
                        <td>${escapeHtml(row.CommentTime || '-')}</td>
                        <td>${escapeHtml(row.MainLanguage || '-')}</td>
                        <td>${escapeHtml(row.Sentiment || '-')}</td>
                        <td>${escapeHtml(row.CommentLikes ?? 0)}</td>
                        <td>${escapeHtml(row.Source || '-')}</td>
                        <td class="result-comment">${escapeHtml(row.NormalizedComment || '')}</td>
                    </tr>
                `).join('');

                if (previewExpandWrap && togglePreviewRowsButton) {
                    previewExpandWrap.hidden = rows.length <= 5;
                    togglePreviewRowsButton.textContent = previewRowsState.expanded ? 'Show first 5 rows' : 'Show all rows';
                }
            }

            function renderSummary(summary) {
                summaryTotalComments.textContent = summary && summary.total_comments !== undefined ? summary.total_comments : '-';
                summaryDistinctPosts.textContent = summary && summary.distinct_posts !== undefined ? summary.distinct_posts : '-';
                summaryAverageLikes.textContent = summary && summary.average_likes !== undefined ? summary.average_likes : '-';
            }

            function renderSqlPreview(filters) {
                const clauses = ['WHERE 1 = 1'];
                Object.entries(filters || {}).forEach(([key, value]) => {
                    if (Array.isArray(value)) {
                        clauses.push(`  AND ${key} IN (${value.map((item) => `'${String(item).replace(/'/g, "''")}'`).join(', ')})`);
                        return;
                    }
                    clauses.push(`  AND ${key} = '${String(value).replace(/'/g, "''")}'`);
                });
                sqlPreview.textContent = `SELECT * FROM [dbo].[EnrichedComments]\n${clauses.join('\n')}\nORDER BY [PostTime] DESC, [CommentTime] DESC;`;
            }

            function getAxisLabelStep(items) {
                const count = Array.isArray(items) ? items.length : 0;
                if (!count) {
                    return 1;
                }
                return Math.max(1, Math.ceil(count / 12));
            }

            function getNumericTickCount(maxValue) {
                if (maxValue <= 10) {
                    return 5;
                }
                if (maxValue <= 100) {
                    return 4;
                }
                return 3;
            }

            function formatAxisValue(value, options) {
                const numericValue = Number(value) || 0;
                const decimals = options && options.percent
                    ? (numericValue >= 10 ? 0 : 1)
                    : (numericValue >= 100 ? 0 : (numericValue >= 10 ? 1 : 2));
                const formatted = numericValue
                    .toFixed(decimals)
                    .replace(/\.0+$/, '')
                    .replace(/(\.\d*[1-9])0+$/, '$1');
                return options && options.percent ? `${formatted}%` : formatted;
            }

            function buildYTicks(maxValue, options) {
                const safeMax = Math.max(Number(maxValue) || 0, 1);
                const tickCount = getNumericTickCount(safeMax);
                return Array.from({ length: tickCount + 1 }, function (_item, index) {
                    const value = (safeMax / tickCount) * index;
                    const y = options.padding.top + options.plotHeight - (value / safeMax) * options.plotHeight;
                    return { value: value, y: y };
                });
            }

            function shouldShowDenseValueLabels(itemCount) {
                return itemCount <= 24;
            }

            function buildSparseValueLabelIndexSet(values) {
                const numericValues = (values || []).map(function (value) { return Number(value) || 0; });
                const count = numericValues.length;
                if (count <= 24) {
                    return new Set(numericValues.map(function (_value, index) { return index; }));
                }

                const maxValue = Math.max(...numericValues, 1);
                const minDistance = count > 80 ? 5 : (count > 50 ? 4 : 3);
                const candidates = numericValues
                    .map(function (value, index) {
                        const prev = index > 0 ? numericValues[index - 1] : -Infinity;
                        const next = index < count - 1 ? numericValues[index + 1] : -Infinity;
                        const isLocalPeak = value >= prev && value >= next;
                        const prominence = value / maxValue;
                        return { index: index, value: value, isLocalPeak: isLocalPeak, prominence: prominence };
                    })
                    .filter(function (item) {
                        return item.value > 0 && item.isLocalPeak && item.prominence >= 0.2;
                    })
                    .sort(function (left, right) {
                        if (right.value !== left.value) {
                            return right.value - left.value;
                        }
                        return left.index - right.index;
                    });

                const chosen = [];
                candidates.forEach(function (candidate) {
                    const tooClose = chosen.some(function (picked) {
                        return Math.abs(picked - candidate.index) < minDistance;
                    });
                    if (!tooClose) {
                        chosen.push(candidate.index);
                    }
                });

                return new Set(chosen);
            }

            function getAdaptiveMeanWindowSize(itemCount, windowBoost) {
                const count = Number(itemCount) || 0;
                const boost = Number(windowBoost) || 0;
                if (count <= 20) {
                    return 1;
                }
                if (count <= 45) {
                    return 3 + boost;
                }
                if (count <= 90) {
                    return 5 + boost;
                }
                return 7 + boost;
            }

            function buildAdaptiveMeanSeries(items, valueKeys, windowBoost) {
                const sourceItems = Array.isArray(items) ? items : [];
                const keys = Array.isArray(valueKeys) ? valueKeys : [valueKeys];
                const windowSize = getAdaptiveMeanWindowSize(sourceItems.length, windowBoost);
                if (windowSize <= 1) {
                    return sourceItems;
                }

                const halfWindow = Math.floor(windowSize / 2);
                return sourceItems.map(function (item, index) {
                    const start = Math.max(0, index - halfWindow);
                    const end = Math.min(sourceItems.length, index + halfWindow + 1);
                    const windowItems = sourceItems.slice(start, end);
                    const nextItem = Object.assign({}, item);

                    keys.forEach(function (key) {
                        const avg = windowItems.reduce(function (sum, currentItem) {
                            return sum + (Number(currentItem[key]) || 0);
                        }, 0) / Math.max(windowItems.length, 1);
                        nextItem[key] = Math.round(avg * 100) / 100;
                    });

                    return nextItem;
                });
            }

            function buildTrendPath(values, width, height, padding, maxValue, yOffset, valueScale) {
                if (!values.length) {
                    return '';
                }

                const windowSize = values.length > 20 ? 5 : 3;
                const smoothed = values.map(function (_value, index) {
                    const start = Math.max(0, index - Math.floor(windowSize / 2));
                    const end = Math.min(values.length, index + Math.floor(windowSize / 2) + 1);
                    const slice = values.slice(start, end);
                    return slice.reduce(function (sum, item) { return sum + item; }, 0) / slice.length;
                });

                const plotWidth = width - padding.left - padding.right;
                const plotHeight = height - padding.top - padding.bottom;
                const xStep = values.length > 1 ? plotWidth / (values.length - 1) : plotWidth;

                return smoothed.map(function (value, index) {
                    const x = padding.left + (index * xStep);
                    const scaledValue = Math.min(Math.max(maxValue, 1), (value || 0) * (valueScale || 1));
                    const baseY = padding.top + plotHeight - (scaledValue / Math.max(maxValue, 1)) * plotHeight;
                    const y = Math.max(padding.top + 6, baseY - (yOffset || 0));
                    return (index === 0 ? 'M' : 'L') + x + ' ' + y;
                }).join(' ');
            }

            function buildBarChartSvg(items, options) {
                const width = 620;
                const height = 260;
                const padding = { top: 18, right: 18, bottom: 64, left: 42 };
                const plotWidth = width - padding.left - padding.right;
                const plotHeight = height - padding.top - padding.bottom;
                const maxValue = Math.max(...items.map(function (item) { return Number(item.value) || 0; }), 1);
                const yTicks = buildYTicks(maxValue, { padding: padding, plotHeight: plotHeight });
                const barWidth = plotWidth / Math.max(items.length, 1);
                const color = options.color || '#5fb3b3';
                const trendPath = options.showTrend
                    ? buildTrendPath(
                        items.map(function (item) { return Number(item.value) || 0; }),
                        width,
                        height,
                        padding,
                        maxValue,
                        options.trendOffset || 10,
                        options.trendScale || 1
                    )
                    : '';
                const labelStep = getAxisLabelStep(items);
                const showValueLabels = shouldShowDenseValueLabels(items.length);
                const labeledValueIndexes = buildSparseValueLabelIndexSet(items.map(function (item) { return item.value; }));

                const bars = items.map(function (item, index) {
                    const value = Number(item.value) || 0;
                    const h = (value / maxValue) * plotHeight;
                    const x = padding.left + index * barWidth + barWidth * 0.15;
                    const y = padding.top + plotHeight - h;
                    const w = barWidth * 0.7;
                    const showLabel = index % labelStep === 0;
                    const barContent = `
                        <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="4" fill="${color}"></rect>
                        ${showLabel ? `<text x="${x + w / 2}" y="${padding.top + plotHeight + 18}" text-anchor="middle" fill="rgba(255,255,255,0.72)" font-size="10">${escapeHtml(item.label)}</text>` : ''}
                        ${showValueLabels || labeledValueIndexes.has(index) ? `<text x="${x + w / 2}" y="${y - 6}" text-anchor="middle" fill="rgba(255,255,255,0.88)" font-size="10">${formatAxisValue(value)}</text>` : ''}
                    `;
                    if (item.post_href) {
                        return `
                            <a href="${escapeHtml(item.post_href)}" target="_blank" rel="noopener noreferrer">
                                <title>Open post ${escapeHtml(item.label)}</title>
                                ${barContent}
                            </a>
                        `;
                    }
                    return `
                        ${barContent}
                    `;
                }).join('');

                return `
                    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(options.title)}">
                        ${yTicks.map(function (tick) {
                            return `<line x1="${padding.left}" y1="${tick.y}" x2="${width - padding.right}" y2="${tick.y}" stroke="rgba(255,255,255,0.08)"></line>`;
                        }).join('')}
                        <line x1="${padding.left}" y1="${padding.top + plotHeight}" x2="${width - padding.right}" y2="${padding.top + plotHeight}" stroke="rgba(255,255,255,0.18)"></line>
                        <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${padding.top + plotHeight}" stroke="rgba(255,255,255,0.18)"></line>
                        ${yTicks.map(function (tick) {
                            return `<text x="${padding.left - 8}" y="${tick.y + 4}" text-anchor="end" fill="rgba(255,255,255,0.64)" font-size="10">${formatAxisValue(tick.value)}</text>`;
                        }).join('')}
                        ${trendPath ? `<path d="${trendPath}" fill="none" stroke="rgba(255,255,255,0.38)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>` : ''}
                        ${bars}
                    </svg>
                `;
            }

            function buildStackedBarChartSvg(items, options) {
                const keys = options.keys;
                const colors = options.colors;
                const width = 620;
                const height = 260;
                const padding = { top: 18, right: 18, bottom: 64, left: 42 };
                const plotWidth = width - padding.left - padding.right;
                const plotHeight = height - padding.top - padding.bottom;
                const maxValue = Math.max(...items.map(function (item) {
                    return keys.reduce(function (sum, key) { return sum + (Number(item[key]) || 0); }, 0);
                }), 1);
                const yTicks = buildYTicks(maxValue, { padding: padding, plotHeight: plotHeight });
                const barWidth = plotWidth / Math.max(items.length, 1);
                const trendPaths = (options.trendSeries || []).map(function (series) {
                    return {
                        color: series.color,
                        path: buildTrendPath(
                            items.map(function (item) { return Number(item[series.key]) || 0; }),
                            width,
                            height,
                            padding,
                            maxValue,
                            options.trendOffset || 10,
                            series.scale != null ? series.scale : (options.trendScale || 1)
                        )
                    };
                });
                const labelStep = getAxisLabelStep(items);
                const showValueLabels = shouldShowDenseValueLabels(items.length);
                const labeledValueIndexes = buildSparseValueLabelIndexSet(items.map(function (item) {
                    return keys.reduce(function (sum, key) { return sum + (Number(item[key]) || 0); }, 0);
                }));

                const bars = items.map(function (item, index) {
                    let runningHeight = 0;
                    const x = padding.left + index * barWidth + barWidth * 0.15;
                    const w = barWidth * 0.7;
                    const total = keys.reduce(function (sum, key) { return sum + (Number(item[key]) || 0); }, 0);
                    const showLabel = index % labelStep === 0;
                    const segments = keys.map(function (key) {
                        const value = Number(item[key]) || 0;
                        const h = (value / maxValue) * plotHeight;
                        const y = padding.top + plotHeight - runningHeight - h;
                        runningHeight += h;
                        return `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${colors[key]}"></rect>`;
                    }).join('');

                    const stackedContent = `
                        ${segments}
                        ${showLabel ? `<text x="${x + w / 2}" y="${padding.top + plotHeight + 18}" text-anchor="middle" fill="rgba(255,255,255,0.72)" font-size="10">${escapeHtml(item.label)}</text>` : ''}
                        ${showValueLabels || labeledValueIndexes.has(index) ? `<text x="${x + w / 2}" y="${padding.top + plotHeight - runningHeight - 6}" text-anchor="middle" fill="rgba(255,255,255,0.88)" font-size="10">${formatAxisValue(total)}</text>` : ''}
                    `;
                    if (item.post_href) {
                        return `
                            <a href="${escapeHtml(item.post_href)}" target="_blank" rel="noopener noreferrer">
                                <title>Open post ${escapeHtml(item.label)}</title>
                                ${stackedContent}
                            </a>
                        `;
                    }
                    return stackedContent;
                }).join('');

                return `
                    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(options.title)}">
                        ${yTicks.map(function (tick) {
                            return `<line x1="${padding.left}" y1="${tick.y}" x2="${width - padding.right}" y2="${tick.y}" stroke="rgba(255,255,255,0.08)"></line>`;
                        }).join('')}
                        <line x1="${padding.left}" y1="${padding.top + plotHeight}" x2="${width - padding.right}" y2="${padding.top + plotHeight}" stroke="rgba(255,255,255,0.18)"></line>
                        <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${padding.top + plotHeight}" stroke="rgba(255,255,255,0.18)"></line>
                        ${yTicks.map(function (tick) {
                            return `<text x="${padding.left - 8}" y="${tick.y + 4}" text-anchor="end" fill="rgba(255,255,255,0.64)" font-size="10">${formatAxisValue(tick.value)}</text>`;
                        }).join('')}
                        ${trendPaths.map(function (trend) {
                            return trend.path
                                ? `<path d="${trend.path}" fill="none" stroke="${trend.color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" opacity="0.95"></path>`
                                : '';
                        }).join('')}
                        ${bars}
                    </svg>
                `;
            }

            function buildGroupedBarChartSvg(items, options) {
                const width = 620;
                const height = 260;
                const padding = { top: 18, right: 18, bottom: 64, left: 42 };
                const plotWidth = width - padding.left - padding.right;
                const plotHeight = height - padding.top - padding.bottom;
                const groups = Array.from(new Set(items.map(function (item) { return item.label; })));
                const sentiments = options.series;
                const maxValue = Math.max(...items.map(function (item) { return Number(item.value) || 0; }), 1);
                const groupWidth = plotWidth / Math.max(groups.length, 1);
                const barWidth = (groupWidth * 0.78) / Math.max(sentiments.length, 1);

                const bars = groups.map(function (group, groupIndex) {
                    const x0 = padding.left + groupIndex * groupWidth + groupWidth * 0.11;
                    const groupItems = items.filter(function (item) { return item.label === group; });
                    const inner = sentiments.map(function (seriesName, seriesIndex) {
                        const match = groupItems.find(function (item) { return item.sentiment === seriesName; });
                        const value = match ? (Number(match.value) || 0) : 0;
                        const h = (value / maxValue) * plotHeight;
                        const x = x0 + seriesIndex * barWidth;
                        const y = padding.top + plotHeight - h;
                        return `<rect x="${x}" y="${y}" width="${barWidth - 2}" height="${h}" rx="3" fill="${options.colors[seriesName]}"></rect>`;
                    }).join('');
                    return `
                        ${inner}
                        <text x="${x0 + (groupWidth * 0.78) / 2}" y="${padding.top + plotHeight + 18}" text-anchor="middle" fill="rgba(255,255,255,0.72)" font-size="10">${escapeHtml(group)}</text>
                    `;
                }).join('');

                return `
                    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(options.title)}">
                        <line x1="${padding.left}" y1="${padding.top + plotHeight}" x2="${width - padding.right}" y2="${padding.top + plotHeight}" stroke="rgba(255,255,255,0.18)"></line>
                        <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${padding.top + plotHeight}" stroke="rgba(255,255,255,0.18)"></line>
                        ${bars}
                    </svg>
                `;
            }

            function buildLineChartSvg(seriesList, options) {
                const width = 620;
                const height = 280;
                const padding = { top: 18, right: 18, bottom: 52, left: 42 };
                const plotWidth = width - padding.left - padding.right;
                const plotHeight = height - padding.top - padding.bottom;
                const axisLabels = Array.from(new Set(seriesList.flatMap(function (series) {
                    return (series.points || []).map(function (point) { return String(point.label || ''); });
                }))).sort(function (left, right) {
                    const leftNumber = Number(left);
                    const rightNumber = Number(right);
                    const leftIsNumber = Number.isFinite(leftNumber);
                    const rightIsNumber = Number.isFinite(rightNumber);
                    if (leftIsNumber && rightIsNumber) {
                        return leftNumber - rightNumber;
                    }
                    return left.localeCompare(right, undefined, { numeric: true });
                });
                const xStep = axisLabels.length > 1 ? plotWidth / (axisLabels.length - 1) : plotWidth;
                const labelToIndex = new Map(axisLabels.map(function (label, index) { return [label, index]; }));
                const maxValue = options.maxValue || Math.max(...seriesList.flatMap(function (series) {
                    return series.points.map(function (point) { return Number(point.value) || 0; });
                }), 1);
                const yTicks = buildYTicks(maxValue, { padding: padding, plotHeight: plotHeight });

                const lines = seriesList.map(function (series) {
                    const points = series.points.map(function (point) {
                        const axisIndex = labelToIndex.get(String(point.label || '')) || 0;
                        const x = padding.left + (axisIndex * xStep);
                        const y = padding.top + plotHeight - ((Number(point.value) || 0) / maxValue) * plotHeight;
                        return { x: x, y: y };
                    });
                    const path = points.map(function (point, index) {
                        return (index === 0 ? 'M' : 'L') + point.x + ' ' + point.y;
                    }).join(' ');
                    const dots = points.map(function (point) {
                        return `<circle cx="${point.x}" cy="${point.y}" r="3.5" fill="${series.color}"></circle>`;
                    }).join('');
                    return `<path d="${path}" fill="none" stroke="${series.color}" stroke-width="2.5"></path>${dots}`;
                }).join('');

                const labelStep = getAxisLabelStep(axisLabels);
                const labels = axisLabels.map(function (label, index) {
                    if (index % labelStep !== 0) {
                        return '';
                    }
                    const x = padding.left + (index * xStep);
                    return `<text x="${x}" y="${padding.top + plotHeight + 18}" text-anchor="middle" fill="rgba(255,255,255,0.72)" font-size="10">${escapeHtml(label)}</text>`;
                }).join('');

                return `
                    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(options.title)}">
                        ${yTicks.map(function (tick) {
                            return `<line x1="${padding.left}" y1="${tick.y}" x2="${width - padding.right}" y2="${tick.y}" stroke="rgba(255,255,255,0.08)"></line>`;
                        }).join('')}
                        <line x1="${padding.left}" y1="${padding.top + plotHeight}" x2="${width - padding.right}" y2="${padding.top + plotHeight}" stroke="rgba(255,255,255,0.18)"></line>
                        <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${padding.top + plotHeight}" stroke="rgba(255,255,255,0.18)"></line>
                        ${yTicks.map(function (tick) {
                            return `<text x="${padding.left - 8}" y="${tick.y + 4}" text-anchor="end" fill="rgba(255,255,255,0.64)" font-size="10">${formatAxisValue(tick.value, { percent: options.percent })}</text>`;
                        }).join('')}
                        ${lines}
                        ${labels}
                    </svg>
                `;
            }

            function renderLegend(items) {
                return `<div class="analysis-legend">${items.map(function (item) {
                    return `<span><i style="background:${item.color}"></i>${escapeHtml(item.label)}</span>`;
                }).join('')}</div>`;
            }

            function renderAdvancedCharts(analysis) {
                if (!advancedChartRoot || !chartStatus) {
                    return;
                }

                if (!analysis || !analysis.summary || !analysis.charts) {
                    advancedChartRoot.hidden = true;
                    advancedChartRoot.innerHTML = '';
                    chartStatus.textContent = 'No chartable data is available for the current filter set.';
                    chartStatus.className = 'status-text';
                    return;
                }

                const charts = analysis.charts || {};
                const visibility = (analysis.chart_visibility && analysis.chart_visibility.visible) || {};
                const hiddenReasons = Object.values((analysis.chart_visibility && analysis.chart_visibility.reasons) || {});
                const sentimentColors = { positive: '#4dbb7c', neutral: '#f2c14e', negative: '#e76f51' };
                const languageTrendColors = ['#8ecae6', '#ffb703', '#fb8500'];
                const trendSeries = (charts.positivity_trend_by_language || []).map(function (series, index) {
                    return {
                        name: series.name,
                        color: languageTrendColors[index % languageTrendColors.length],
                        points: series.points || []
                    };
                });
                const solidarityTrendSeries = (charts.solidarity_trend_by_language || []).map(function (series, index) {
                    return {
                        name: series.name,
                        color: languageTrendColors[index % languageTrendColors.length],
                        points: series.points || []
                    };
                });

                const cards = [];

                if (visibility.comments_by_post) {
                    cards.push(`
                        <article class="analysis-chart-card span-two">
                            <h3>Comments by post</h3>
                            ${buildBarChartSvg((charts.comments_by_post || []).map(function (item) {
                                return {
                                    label: String(item.label || '').replace(/^P/, ''),
                                    value: item.value,
                                    post_href: item.post_href
                                };
                            }), { title: 'Comments by post', color: '#6ac3ff', showTrend: true, trendOffset: 16 })}
                            <p class="analysis-chart-note">Post-level volume after the current advanced filters.</p>
                        </article>
                    `);
                }

                if (visibility.comments_by_language) {
                    cards.push(`
                        <article class="analysis-chart-card">
                            <h3>Comments by language</h3>
                            ${buildBarChartSvg(charts.comments_by_language || [], { title: 'Comments by language', color: '#ff9f68' })}
                            <p class="analysis-chart-note">Language split of the filtered subset.</p>
                        </article>
                    `);
                }

                if (visibility.sentiment_by_language) {
                    cards.push(`
                        <article class="analysis-chart-card">
                            <h3>Sentiment by language</h3>
                            ${buildStackedBarChartSvg(charts.sentiment_by_language || [], { title: 'Sentiment by language', keys: ['positive', 'neutral', 'negative'], colors: sentimentColors })}
                            ${renderLegend([{ label: 'Positive', color: sentimentColors.positive }, { label: 'Neutral', color: sentimentColors.neutral }, { label: 'Negative', color: sentimentColors.negative }])}
                        </article>
                    `);
                }

                if (visibility.sentiment_by_post) {
                    cards.push(`
                        <article class="analysis-chart-card span-two">
                            <h3>Sentiment by post</h3>
                            ${buildStackedBarChartSvg((charts.sentiment_by_post || []).map(function (item) {
                                return {
                                    label: String(item.label || '').replace(/^P/, ''),
                                    positive: item.positive,
                                    neutral: item.neutral,
                                    negative: item.negative,
                                    post_href: item.post_href,
                                    positive_share: item.positive_share,
                                    neutral_share: item.neutral_share,
                                    negative_share: item.negative_share
                                };
                            }), {
                                title: 'Sentiment by post',
                                keys: ['positive', 'neutral', 'negative'],
                                colors: sentimentColors,
                                trendSeries: [
                                    { key: 'positive_share', color: '#9be2b0', scale: 4.6 },
                                    { key: 'neutral_share', color: '#ffe08a', scale: 4.6 },
                                    { key: 'negative_share', color: '#ff9c7f', scale: 4.6 }
                                ],
                                trendOffset: 28,
                                trendScale: 4.6
                            })}
                            ${renderLegend([{ label: 'Positive', color: sentimentColors.positive }, { label: 'Neutral', color: sentimentColors.neutral }, { label: 'Negative', color: sentimentColors.negative }])}
                        </article>
                    `);
                }

                if (visibility.comment_length_histogram) {
                    cards.push(`
                        <article class="analysis-chart-card">
                            <h3>Comment length histogram</h3>
                            ${buildBarChartSvg(charts.comment_length_histogram || [], { title: 'Comment length histogram', color: '#b388eb' })}
                            <p class="analysis-chart-note">Distribution of filtered comment length in words.</p>
                        </article>
                    `);
                }

                if (visibility.avg_length_by_sentiment) {
                    cards.push(`
                        <article class="analysis-chart-card">
                            <h3>Average length by sentiment</h3>
                            ${buildBarChartSvg(charts.avg_length_by_sentiment || [], { title: 'Average length by sentiment', color: '#7bd389' })}
                            <p class="analysis-chart-note">Average words per comment for each sentiment bucket.</p>
                        </article>
                    `);
                }

                if (visibility.avg_length_by_language_sentiment) {
                    cards.push(`
                        <article class="analysis-chart-card">
                            <h3>Average length by language and sentiment</h3>
                            ${buildGroupedBarChartSvg(charts.avg_length_by_language_sentiment || [], { title: 'Average length by language and sentiment', series: ['positive', 'neutral', 'negative'], colors: sentimentColors })}
                            ${renderLegend([{ label: 'Positive', color: sentimentColors.positive }, { label: 'Neutral', color: sentimentColors.neutral }, { label: 'Negative', color: sentimentColors.negative }])}
                        </article>
                    `);
                }

                if (visibility.solidarity_distribution_by_language) {
                    cards.push(`
                        <article class="analysis-chart-card">
                            <h3>Average solidarity by language</h3>
                            ${buildBarChartSvg(charts.solidarity_distribution_by_language || [], { title: 'Average solidarity by language', color: '#f28482' })}
                            <p class="analysis-chart-note">Average within-post alignment with the anchor comment sentiment.</p>
                        </article>
                    `);
                }

                if (visibility.positivity_trend_overall) {
                    cards.push(`
                        <article class="analysis-chart-card">
                            <h3>Overall positivity trend</h3>
                            ${buildLineChartSvg([{ name: 'overall', color: '#90be6d', points: buildAdaptiveMeanSeries((charts.positivity_trend_overall || []).map(function (point) {
                                return { label: String(point.label || '').replace(/^P/, ''), value: point.value };
                            }), 'value') }], { title: 'Overall positivity trend', maxValue: 100, percent: true })}
                            ${renderLegend([{ label: 'Overall positivity', color: '#90be6d' }])}
                            <p class="analysis-chart-note">Displayed with an adaptive moving average based on the number of analyzed posts.</p>
                        </article>
                    `);
                }

                if (visibility.positivity_trend_by_language && trendSeries.length) {
                    cards.push(`
                        <article class="analysis-chart-card">
                            <h3>Positivity trend by top languages</h3>
                            ${buildLineChartSvg(trendSeries.map(function (series) {
                                return {
                                    name: series.name,
                                    color: series.color,
                                    points: buildAdaptiveMeanSeries((series.points || []).map(function (point) {
                                        return { label: String(point.label || '').replace(/^P/, ''), value: point.value };
                                    }), 'value', 2)
                                };
                            }), { title: 'Positivity trend by language', maxValue: 100, percent: true })}
                            ${renderLegend(trendSeries.map(function (series) { return { label: series.name, color: series.color }; }))}
                            <p class="analysis-chart-note">Displayed with an adaptive moving average based on the number of analyzed posts.</p>
                        </article>
                    `);
                }

                if (visibility.solidarity_trend_overall && (charts.solidarity_trend_overall || []).length) {
                    cards.push(`
                        <article class="analysis-chart-card">
                            <h3>Overall solidarity trend</h3>
                            ${buildLineChartSvg([{ name: 'overall solidarity', color: '#f28482', points: buildAdaptiveMeanSeries((charts.solidarity_trend_overall || []).map(function (point) {
                                return { label: String(point.label || '').replace(/^P/, ''), value: point.value };
                            }), 'value') }], { title: 'Overall solidarity trend', maxValue: 100, percent: true })}
                            ${renderLegend([{ label: 'Overall solidarity', color: '#f28482' }])}
                            <p class="analysis-chart-note">Displayed with an adaptive moving average based on the number of analyzed posts.</p>
                        </article>
                    `);
                }

                if (visibility.solidarity_trend_by_language && solidarityTrendSeries.length) {
                    cards.push(`
                        <article class="analysis-chart-card">
                            <h3>Solidarity trend by top languages</h3>
                            ${buildLineChartSvg(solidarityTrendSeries.map(function (series) {
                                return {
                                    name: series.name,
                                    color: series.color,
                                    points: buildAdaptiveMeanSeries((series.points || []).map(function (point) {
                                        return { label: String(point.label || '').replace(/^P/, ''), value: point.value };
                                    }), 'value', 2)
                                };
                            }), { title: 'Solidarity trend by language', maxValue: 100, percent: true })}
                            ${renderLegend(solidarityTrendSeries.map(function (series) { return { label: series.name, color: series.color }; }))}
                            <p class="analysis-chart-note">Displayed with an adaptive moving average based on the number of analyzed posts.</p>
                        </article>
                    `);
                }

                if (!cards.length) {
                    advancedChartRoot.hidden = true;
                    advancedChartRoot.innerHTML = '';
                    chartStatus.textContent = hiddenReasons[0] || 'The current filter set leaves no meaningful charts to display.';
                    chartStatus.className = 'status-text';
                    return;
                }

                advancedChartRoot.hidden = false;
                advancedChartRoot.innerHTML = cards.join('');
                chartStatus.textContent = hiddenReasons.length
                    ? `Some charts were hidden because of the active filters. ${hiddenReasons.join(' ')}`
                    : 'Showing all charts that remain meaningful for the current subset.';
                chartStatus.className = 'status-text';
            }

            async function loadFilteredAnalysis(payload) {
                chartStatus.textContent = 'Building charts for the current filtered subset...';
                chartStatus.className = 'status-text';
                advancedChartRoot.hidden = true;

                try {
                    const rawResponse = await session.fetchWithCsrf('/api/advanced-analysis/analyze', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify(payload)
                    });

                    const response = await session.ensureAuthenticatedResponse(rawResponse);
                    if (!response) {
                        return;
                    }

                    const data = await response.json();
                    if (!response.ok) {
                        throw new Error(data.error || 'Chart analysis request failed.');
                    }

                    renderAdvancedCharts(data.analysis);
                } catch (error) {
                    renderAdvancedCharts(null);
                    chartStatus.textContent = error.message;
                    chartStatus.className = 'status-text is-error';
                }
            }

            function syncPageSelectors(changedField) {
                if (!pageNameInputs.length || !pageIdInputs.length) {
                    return;
                }

                const hasPageName = pageNameInputs.some((input) => input.checked);
                const hasPageId = pageIdInputs.some((input) => input.checked);

                if (changedField === 'page_name' && hasPageName) {
                    pageIdInputs.forEach((input) => {
                        input.checked = false;
                    });
                }

                if (changedField === 'page_id' && hasPageId) {
                    pageNameInputs.forEach((input) => {
                        input.checked = false;
                    });
                }

                refreshChecklistSelectionState();
            }

            function syncAllOptionForGroup(groupName, changedInput) {
                const inputs = Array.from(document.querySelectorAll(`input[name="${groupName}"]`));
                if (!inputs.length) {
                    return;
                }

                const allInput = inputs.find((input) => input.value === '__all__');
                const specificInputs = inputs.filter((input) => input.value !== '__all__');

                if (!allInput) {
                    return;
                }

                if (changedInput === allInput && allInput.checked) {
                    specificInputs.forEach((input) => {
                        input.checked = false;
                    });
                    return;
                }

                const anySpecificChecked = specificInputs.some((input) => input.checked);
                if (anySpecificChecked) {
                    allInput.checked = false;
                    return;
                }

                allInput.checked = true;
            }

            function refreshChecklistSelectionState() {
                Array.from(document.querySelectorAll('.filter-checklist input[type="checkbox"]')).forEach((input) => {
                    const label = input.closest('label');
                    if (!label) {
                        return;
                    }
                    label.classList.toggle('is-selected', input.checked);
                });
            }

            async function loadPreview() {
                const payload = buildPayload();
                queryStatus.textContent = 'Loading preview from EnrichedComments...';
                queryStatus.className = 'status-text';
                renderSqlPreview(payload);
                previewRowsState.expanded = false;
                if (queryLoading) {
                    queryLoading.hidden = false;
                }

                if (queryPreviewSection) {
                    queryPreviewSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }

                try {
                    const rawResponse = await session.fetchWithCsrf('/api/advanced-analysis/preview', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify(payload)
                    });

                    const response = await session.ensureAuthenticatedResponse(rawResponse);
                    if (!response) {
                        return;
                    }

                    const data = await response.json();
                    if (!response.ok) {
                        throw new Error(data.error || 'Preview request failed.');
                    }

                    renderSummary(data.summary);
                    renderAppliedFilters(data.applied_filters);
                    renderRows(data.rows);
                    await loadFilteredAnalysis(payload);

                    queryStatus.textContent = `Preview loaded: ${data.rows.length} rows shown, ${data.summary.total_comments} total matches.`;
                    queryStatus.className = 'status-text is-success';
                } catch (error) {
                    renderSummary(null);
                    renderAppliedFilters(payload);
                    renderRows([]);
                    renderAdvancedCharts(null);
                    queryStatus.textContent = error.message;
                    queryStatus.className = 'status-text is-error';
                } finally {
                    if (queryLoading) {
                        queryLoading.hidden = true;
                    }
                }
            }

            if (advancedQueryForm) {
                advancedQueryForm.addEventListener('submit', (event) => {
                    event.preventDefault();
                    loadPreview();
                });
            }

            if (pageNameInputs.length) {
                pageNameInputs.forEach((input) => input.addEventListener('change', () => {
                    syncAllOptionForGroup('page_name', input);
                    syncPageSelectors('page_name');
                }));
            }

            if (pageIdInputs.length) {
                pageIdInputs.forEach((input) => input.addEventListener('change', () => {
                    syncAllOptionForGroup('page_id', input);
                    syncPageSelectors('page_id');
                }));
            }

            ['source', 'language', 'sentiment', 'first_comment_sentiment'].forEach((groupName) => {
                Array.from(document.querySelectorAll(`input[name="${groupName}"]`)).forEach((input) => {
                    input.addEventListener('change', () => {
                        syncAllOptionForGroup(groupName, input);
                        refreshChecklistSelectionState();
                    });
                });
            });

            if (resetFiltersButton && advancedQueryForm) {
                resetFiltersButton.addEventListener('click', () => {
                    advancedQueryForm.reset();
                    syncPageSelectors();
                    renderSqlPreview({});
                    renderAppliedFilters({});
                    renderSummary(null);
                    previewRowsState = { rows: [], expanded: false };
                    renderRows([]);
                    renderAdvancedCharts(null);
                    queryStatus.textContent = 'Filters reset. Submit again to preview rows.';
                    queryStatus.className = 'status-text';
                    if (queryLoading) {
                        queryLoading.hidden = true;
                    }
                });
            }

            if (togglePreviewRowsButton) {
                togglePreviewRowsButton.addEventListener('click', () => {
                    previewRowsState.expanded = !previewRowsState.expanded;
                    renderRows(previewRowsState.rows);
                });
            }

            ['page_name', 'page_id', 'source', 'language', 'sentiment', 'first_comment_sentiment'].forEach((groupName) => {
                syncAllOptionForGroup(groupName);
            });
            syncPageSelectors();
            refreshChecklistSelectionState();
            renderAppliedFilters({});

