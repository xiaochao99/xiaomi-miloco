/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import ThoughtContent from '../ThoughtContent';
import FinalAnswerContent from '../FinalAnswerContent';
import { parseStreamContent } from '../utils';

/**
 * StreamMessage Component - Stream message component
 * 流式消息组件
 *
 * @param {Object} data - The data to display
 * @param {boolean} isAccumulating - The is accumulating
 * @returns {JSX.Element} Stream message component
 */
const StreamMessage = ({ data, isAccumulating = false }) => {
  const { stream } = data;
  const [displayText, setDisplayText] = useState('');
  const [_isTyping, setIsTyping] = useState(false);

  useEffect(() => {
    if (!stream) {return;}

    if (isAccumulating && stream !== displayText) {
      setIsTyping(true);
      setDisplayText(stream);
      const timer = setTimeout(() => {
        setIsTyping(false);
      }, 100);

      return () => clearTimeout(timer);
    } else if (!isAccumulating) {
      setDisplayText(stream);
      setIsTyping(false);
    }
  }, [stream, isAccumulating]);

  const parsed = parseStreamContent(displayText);

  if (parsed.hasStructure) {
    return (
      <div style={{ margin: '0px' }}>
        {parsed.segments.map((segment, index) => {
          switch (segment.type) {
            case 'reflect': {
              return (
                <ThoughtContent
                  key={index}
                  content={segment.content}
                  status={segment.isComplete ? 'completed' : 'reflect'}
                />
              );
            }
            case 'final_answer':
              return (
                <FinalAnswerContent
                  key={index}
                  content={segment.content}
                />
              );
            case 'text':
              return (
                <div key={index} style={{
                  margin: '8px 0',
                  lineHeight: '1.6',
                  fontSize: '16px',
                  color: 'var(--text-color)'
                }}>
                  <ReactMarkdown
                    components={{
                      p: ({children}) => <p style={{}}>{children}</p>
                    }}
                  >
                    {segment.content}
                  </ReactMarkdown>
                </div>
              );
            default:
              return null;
          }
        })}
      </div>
    );
  }

  return (
    <div style={{
      padding: '0',
      lineHeight: '1.5',
      fontSize: '14px',
      color: 'var(--text-color)',
      whiteSpace: 'pre-wrap',
      wordBreak: 'break-word'
    }}>
      <ReactMarkdown
        components={{
          p: ({children}) => <p style={{ margin: '0'}}>{children}</p>,
        }}
      >
        {displayText}
      </ReactMarkdown>
    </div>
  );
};

export default StreamMessage;
